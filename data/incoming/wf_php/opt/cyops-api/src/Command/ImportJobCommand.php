<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Command;

use App\Constants\AppConstants;
use DateTime;
use Exception;
use ZipArchive;
use Ramsey\Uuid\Uuid;
use App\Entity\Core\File;
use App\Entity\Core\PgFile;
use InvalidArgumentException;
use App\Entity\Core\ImportJob;
use App\Service\SettingsHelper;
use App\Entity\Core\SolutionPack;
use App\Entity\Core\ExportTemplate;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Component\Filesystem\Filesystem;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputOption;

use App\Service\ConfigExportImport\ImportService;
use Symfony\Component\Console\Style\SymfonyStyle;
use Symfony\Component\Console\Input\InputInterface;
use App\EventSubscriber\MqMessagebroadcastSubscriber;
use Symfony\Component\Console\Output\OutputInterface;
use Symfony\Component\Filesystem\Exception\IOException;
use App\Service\ConfigExportImport\ImportOptionsGenerator;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Class ImportJobCommand
 */
class ImportJobCommand extends Command
{
    const STATUS = array(
        "DRAFT" => "Draft",
        "GENERATING_OPTIONS" => "Generating Options",
        "OPTIONS_GENERATED" => "Reviewing",
        "IMPORTING" => "In Progress",
        "PUBLISHING" => "Publishing Modules",
        "ERROR" => "Error",
        "IMPORT_COMPLETE" => "Import Complete"
    );

    /** @var Filesystem $filesystem */
    protected $filesystem;

    /** @var ContainerInterface */
    private $container;

    private $settingsHelper;
    private $entityManager;
    private $importService;

    private $importOptionsGenerator;

    public function __construct(
        SettingsHelper $settingsHelper,
        EntityManagerInterface $entityManager,
        ImportService $importService,
        ImportOptionsGenerator $importOptionsGenerator,
        ContainerInterface $container
    ) {
        $this->settingsHelper = $settingsHelper;
        $this->entityManager = $entityManager;
        $this->importService = $importService;
        $this->importOptionsGenerator = $importOptionsGenerator;
        $this->container = $container;
        parent::__construct();
    }

    protected function configure()
    {
        $this
            ->setName('fortisoar:jobs:import')
            ->setDescription('Imports records and configuration from a Zip/JSON file')
            ->setDefinition([
                new InputOption(
                    'job-uuid',
                    'j',
                    InputOption::VALUE_REQUIRED | InputOption::VALUE_IS_ARRAY,
                    'The uuid of the import job that will be started.'
                ),
                new InputOption(
                    'generate-options',
                    'o',
                    InputOption::VALUE_NONE,
                    'Will update the Import Job record with an options object for user input.'
                ),
                new InputOption(
                    'user-token',
                    'ut',
                    InputOption::VALUE_OPTIONAL,
                    'The user token for the import context. If empty, the appliance user will be used.'
                ),
                new InputOption(
                    'token-type',
                    'tt',
                    InputOption::VALUE_OPTIONAL,
                    'Type of token HMAC or JWT.'
                ),
                new InputOption(
                    'delete-on-completion',
                    'x',
                    InputOption::VALUE_NONE,
                    'Delete the import job after completing the import.'
                )
            ]);

        $this->filesystem = new Filesystem();
    }

    protected function execute(InputInterface $input, OutputInterface $output)
    {
        $io = new SymfonyStyle($input, $output);
        $importedBy = [];
        $jobUuids = $input->getOption('job-uuid');
        $generateOptions = $input->getOption('generate-options');
        if (empty($jobUuids)) {
            $io->error('Please specify a job uuid');
            return Command::FAILURE;
        }
        $jobUuid = $jobUuids[0];
        $rawToken = $input->getOption('user-token');
        $tokenType = $input->getOption('token-type');
        $deleteOnCompletion = $input->getOption('delete-on-completion');
        if ($rawToken && $tokenType) {
            $this->settingsHelper->setRefreshedToken($rawToken, $tokenType);
        }
        $repository = $this->entityManager->getRepository(ImportJob::class);
        /** @var ImportJob $importJob */
        try {
            $importJob =  $repository->findOneBy(['uuid' => $jobUuid]);
        } catch (InvalidArgumentException | \Exception $e) {
            $io->error($e->getMessage());
        }
        if (!$importJob) {
            throw new \Exception(sprintf('Import Job %s does not exist', $jobUuid));
        }

        try {
            $solutionPackUuid = !is_null($importJob->getSolutionPack()) ? $importJob->getSolutionPack()->getUuid() : false;
            if ($solutionPackUuid) {
                //ToDo : since we have solution record , remove find call in below function and pass the object directly.
                $importedBy = [['apiName' => $importJob->getSolutionPack()->getName(), 'name' => $importJob->getSolutionPack()->getLabel(), 'version' => $importJob->getSolutionPack()->getVersion()]];
            }
            list($folderPath, $isFolder) = $this->loadFolderIntoTmp($importJob);
            // While generating the option disable softDeleteable extension, to check for records in recycle bin too.
            if (array_key_exists('softdeleteable', $this->entityManager->getFilters()->getEnabledFilters())) {
                $this->entityManager->getFilters()->disable('softdeleteable');
            }

            if ($generateOptions) {
                // TODO: fix this for tgz
                $this->generateImportJobOptions($folderPath, $importJob, $io, $tokenType, $isFolder);
                $message = 'Import job options populated successfully';
            } else {
                $this->importConfig($folderPath, $importJob, $io, $tokenType, $isFolder, $importedBy);
                $message = 'Import completed successfully';
                if ($solutionPackUuid) {
                    $this->generateExportTemplate($solutionPackUuid);
                }
            }
            $io->success($message);
            // Clean up
            $this->filesystem->remove($folderPath);
            return Command::SUCCESS;
        } catch (IOException | Exception $e) {
            $message = sprintf('Error while importing file: %s', $e->getMessage());
            $this->updateImportJob($importJob, self::STATUS['ERROR'], null, null, $e->getMessage(), null, $message);
            $io->error($message);
            return Command::FAILURE;
        } finally {
            if ($deleteOnCompletion) {
                $this->deleteImportJob($importJob);
            }
        }
    }

    private function deleteImportJob(ImportJob $importJob)
    {
        $importJobEntityManager = $this->container->get('doctrine')->getManagerForClass(ImportJob::class);
        $importJobEntityManager->remove($importJob);
        $importJobEntityManager->flush();
    }

    private function loadFolderIntoTmp(ImportJob $importJob)
    {
        /** @var string $fileIri */
        $fileIri = $importJob->getFile();
        $explodedIRI = explode('/', $fileIri);
        $fileUuid = end($explodedIRI);

        $repository = $this->entityManager->getRepository(File::class);
        /** @var AbstractFile $file */
        $file =  $repository->findOneBy(['uuid' => $fileUuid]);

        $pgFileUuid = $file->getFile();

        $pgFileRepo = $this->entityManager->getRepository(PgFile::class);
        /** @var AbstractFile $file */
        $pgFile = $pgFileRepo->findOneBy(['uuid' => $pgFileUuid]);
        $folderPath = sprintf('%s/fsrimport-%s/', sys_get_temp_dir(), $pgFileUuid);

        $freeSpace = disk_free_space(sys_get_temp_dir());
        $buffer = 10000000; // 10Mb buffer
        if ($freeSpace - $file->getSize() < $buffer) {
            throw new \Exception(sprintf('Not enough free space in /tmp to import this file. Available: %.1fMb', $freeSpace / 1000000));
        }

        // Support single JSON files
        if ($file->getMimeType() == 'application/json') {
            $jsonFilePath = sprintf('%s/config.json', $folderPath);
            $this->filesystem->mkdir($folderPath);
            $this->filesystem->dumpFile($jsonFilePath, base64_decode(stream_get_contents($pgFile->getFile())));
            return [$folderPath, false];
        } else {
            $this->filesystem->mkdir($folderPath);
            $zipFilePath = sprintf('%sconfig.zip', $folderPath);
            $this->filesystem->dumpFile($zipFilePath, base64_decode(stream_get_contents($pgFile->getFile())));
            $zip = new ZipArchive;
            $zip->open($zipFilePath);
            $zip->extractTo($folderPath);
            $zip->close();

            $folderName = $folderPath . pathinfo($file->getFileName(), PATHINFO_FILENAME) . '/';
            if (!is_dir($folderName)) {
                foreach (scandir($folderPath) as $folder) {
                    if ($folder != "." && $folder != ".." && strpos($folder, '__') === false && is_dir($folderPath . $folder)) {
                        $folderName = $folderPath . $folder . '/';
                    }
                }
            }
            return [$folderName, true];
        }
    }

    private function loadConfigJson($folderPath)
    {
        $configJsonFilePath = sprintf('%s/config.json', $folderPath);
        $jsonData = file_get_contents($configJsonFilePath);
        $jsonObj = json_decode($jsonData, true);
        if (is_null($jsonObj)) {
            throw new \Exception('Config JSON is empty');
        }
        return $jsonObj;
    }

    private function generateImportJobOptions(string $folderPath, ImportJob $importJob, SymfonyStyle $io, $tokenType, $isFolder)
    {
        if (!$isFolder) {
            $jsonObj = $this->loadConfigJson($folderPath);
        }
        // Clear them first
        $this->updateImportJob($importJob, null, 0, [], null, null, []);
        // Generate options for each key
        $this->updateImportJob($importJob, self::STATUS['GENERATING_OPTIONS'], 10, null, null, 'starting', 'Generating Options...');
        if ($isFolder) {
            $options = $this->importOptionsGenerator->generateFromFolder($folderPath, $importJob, $io, $tokenType);
        } else {
            $options = $this->importOptionsGenerator->generate($jsonObj, $importJob, $io, $tokenType);
        }
        // Save options to entity
        $this->updateImportJob($importJob, self::STATUS['OPTIONS_GENERATED'], 100, $options, null, null, 'Import options generated successfully');
    }

    public function updateImportJob(ImportJob $importJob, $status = null, $progressPercent = null, $options = null, $errorMessage = null, $currentlyImporting = null, $logMessage = null)
    {
        $oldData = [
            '@id' => '/api/3/import_jobs/' . $importJob->getUuid()
        ];
        $newData = [
            '@id' => '/api/3/import_jobs/' . $importJob->getUuid()
        ];
        $oldData['id'] = $importJob->getId();
        $newData['id'] = $importJob->getId();
        if ($status !== null) {
            $oldStatus = $importJob->getStatus();
            $importJob->setStatus($status);
            $oldData['status'] = $oldStatus;
            $newData['status'] = $status;
        }
        if ($progressPercent !== null) {
            $oldProgressPercent = $importJob->getProgressPercent();
            $importJob->setProgressPercent($progressPercent);
            $oldData['progressPercent'] = $oldProgressPercent;
            $newData['progressPercent'] = $progressPercent;
        }
        if ($errorMessage !== null) {
            $oldErrorMessage = $importJob->getErrorMessage();
            $importJob->setErrorMessage($errorMessage);
            $oldData['errorMessage'] = $oldErrorMessage;
            $newData['errorMessage'] = $errorMessage;
        }
        if ($options !== null) {
            $oldOptions = $importJob->getOptions();
            $importJob->setOptions($options);
            $oldData['options'] = $oldOptions;
            $newData['options'] = $options;
        }
        if ($currentlyImporting !== null) {
            $old = $importJob->getCurrentlyImporting();
            $importJob->setCurrentlyImporting($currentlyImporting);
            $oldData['currentlyImporting'] = $old;
            $newData['currentlyImporting'] = $currentlyImporting;
        }
        if ($logMessage !== null) {
            if ($logMessage === []) {
                $importJob->clearLogMessages();
            } else {
                $importJob->addLogMessage($logMessage);
            }
            // Don't audit logMessages
        }
        $timestamp = new \DateTime('NOW', new \DateTimeZone('UTC'));
        $importJob->setModifyDate($timestamp);
        $this->entityManager->persist($importJob);
        $this->entityManager->flush();
        $body = $this->prepareChangeData($oldData, $newData, $importJob->getUuid());
        $this->container->get('old_sound_rabbit_mq.cyops_crud_auditing_producer')->setContentType('application/json');
        $this->container->get('old_sound_rabbit_mq.cyops_crud_auditing_producer')->publish(json_encode([$body]), MqMessagebroadcastSubscriber::DEFAULT_KEY);
    }

    private function importConfig(string $folderPath, ImportJob $importJob, SymfonyStyle $io, $tokenType = 'JWT', $isFolder = true, $importedBy = [])
    {
        if (!$isFolder) {
            $jsonObj = $this->loadConfigJson($folderPath);
        }

        $this->updateImportJob($importJob, null, 0, null, null, null, []);
        $this->updateImportJob($importJob, self::STATUS['IMPORTING'], null, null, null, null, 'Beginning import');

        if ($isFolder) {
            $configImportResult = $this->importService->importConfigurationFromFolder($folderPath, $importJob, $io, $tokenType, $importedBy);
        } else {
            $configImportResult = $this->importService->importConfiguration($jsonObj, $importJob, $io, $tokenType);
        }

        if (!$configImportResult['success']) {
            throw new \Exception('Configuration import failed.');
        }
        $command = '/usr/bin/php /opt/cyops-api/bin/console app:cache:clear';
        exec($command, $execOutput, $returnVal);
        $this->updateImportJob($importJob, self::STATUS['IMPORT_COMPLETE'], null, null, null, 'completed', 'Import completed.');
    }

    /**
     * @return array
     */
    protected function prepareChangeData(array $oldData, array $newData, string $entityId)
    {
        $deltaData = [];
        $deltaData['oldData'] = $oldData;
        $deltaData['newData'] = $newData;
        try {
            $user = $this->settingsHelper->getCurrentUser();
            if ($user) {
                $userUUID = $user->getUuid();
                $userName = $this->settingsHelper->extractUserName($user);
            } else {
                $userUUID = 'SYSTEM';
                $userName = 'SYSTEM';
            }
        } catch (InvalidArgumentException | \Exception $e) {
            $userUUID = 'SYSTEM';
            $userName = 'SYSTEM';
        }
        $sourceIp = 'localhost';
        if (isset($_SERVER['HTTP_X_FORWARDED_FOR'])) {
            $sourceIp = $_SERVER['HTTP_X_FORWARDED_FOR'];
        } elseif (isset($_SERVER['REMOTE_ADDR'])) {
            $sourceIp = $_SERVER['REMOTE_ADDR'];
        }
        return [
            AppConstants::COMPONENT => 'crudhub',
            AppConstants::ENTITY_TYPE => 'ImportJob',
            AppConstants::ENTITY_UUID => $entityId,
            AppConstants::HTTP_METHOD => 'Update',
            AppConstants::USER_UUID => $userUUID,
            AppConstants::USER => $userName,
            AppConstants::TRANSACTION_DATE => (int)($_SERVER['REQUEST_TIME_FLOAT'] * 1000),
            AppConstants::DELTA_DATA => $deltaData,
            AppConstants::REMOTE_ADDR => $sourceIp
        ];
    }

    public function generateExportTemplate($solutionPackUuid)
    {
        $filteredOption = [];
        $repository = $this->entityManager->getRepository(SolutionPack::class);
        $solutionRecord =  $repository->findOneBy(['uuid' => $solutionPackUuid]);
        $options = $solutionRecord->getImportJob()->getOptions();
        foreach ($options as $key => $value) {
            $filteredOption[$key] = $value['values'];
        }
        try {
            $result = $this->importService->exportOptionGenerationFromInputOptions($filteredOption);
            $timestamp = new \DateTime('NOW', new \DateTimeZone('UTC'));
            $exportTemplate = new ExportTemplate();
            $exportTemplate->setOptions($result);
            $exportTemplate->setName("FortiSOAR-" . $solutionRecord->getName() . "-" . $solutionRecord->getVersion() . "-" . $timestamp->format('Y-m-d H:i:s'));
            $exportTemplate->setType("SolutionPack Export");
            $exportTemplate->setUuid(Uuid::uuid4()->toString());
            $this->entityManager->persist($exportTemplate);
            $this->entityManager->flush();
            $solutionRecord->setTemplate($exportTemplate);
            $this->entityManager->persist($solutionRecord);
            $this->entityManager->flush();
        } catch (InvalidArgumentException | \Exception $e) {
            return false;
        }
    }
}
