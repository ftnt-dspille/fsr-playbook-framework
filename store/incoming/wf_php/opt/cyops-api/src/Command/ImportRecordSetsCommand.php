<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Command;

use Ramsey\Uuid\Uuid;
use InvalidArgumentException;
use App\Entity\Core\ImportJob;
use App\Service\SettingsHelper;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputOption;
use Symfony\Component\Console\Style\SymfonyStyle;
use App\Service\ConfigExportImport\RecordSetConfig;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Output\OutputInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;

class ImportRecordSetsCommand extends Command
{
    protected static $defaultName = 'app:import:recordsets';

    protected $entityManager;

    private $container;

    private $settingsHelper;

    public function __construct(EntityManagerInterface $entityManager, ContainerInterface $container, SettingsHelper $settingsHelper)
    {
        $this->entityManager = $entityManager;
        $this->container = $container;
        $this->settingsHelper = $settingsHelper;
        parent::__construct();
    }

    protected function configure()
    {
        $this
            ->setDescription('Imports record sets from file, without updating an import job')
            ->setDefinition([
                new InputOption(
                    'tmp-directory',
                    'd',
                    InputOption::VALUE_REQUIRED,
                    'Path to tmp directory with record sets.'
                ),
                new InputOption(
                    'options-json-path',
                    'o',
                    InputOption::VALUE_REQUIRED,
                    'Path to JSON file containing record set options.'
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
                    'user-iri',
                    'u',
                    InputOption::VALUE_OPTIONAL,
                    'The user IRI that should be defaulted for the createUser and modifyUser'
                ),
                new InputOption(
                    'job-uuid',
                    'j',
                    InputOption::VALUE_REQUIRED | InputOption::VALUE_IS_ARRAY,
                    'The uuid of the import job that will be started.'
                ),
            ]);
    }

    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        $io = new SymfonyStyle($input, $output);
        $tmpDirectory = $input->getOption('tmp-directory');
        $optionsJsonPath = $input->getOption('options-json-path');
        $userIri = $input->getOption('user-iri');
        $rawToken = $input->getOption('user-token');
        $tokenType = $input->getOption('token-type');
        $jobUuids = $input->getOption('job-uuid');
        $jobUuid = $jobUuids[0];
        if ($rawToken && $tokenType) {
            $this->settingsHelper->setRefreshedToken($rawToken, $tokenType);
        }

        $repository = $this->entityManager->getRepository(ImportJob::class);
        try {
            /** @var ImportJob $importJob */
            $importJob =  $repository->findOneBy(['uuid' => $jobUuid]);
        } catch (InvalidArgumentException | \Exception $e) {
            $io->error($e->getMessage());
        }
        if (!$importJob) {
            throw new \Exception(sprintf('Import Job %s does not exist', $jobUuid));
        }

        $optionsJson = file_get_contents($optionsJsonPath);
        $options = json_decode($optionsJson, true);

        /** @var RecordSetConfig */
        $recordSetConfig = $this->container->get('fsr.core.service.record_set_config');
        $key = 'recordSets';
        $recordSetConfig->setImportUser($userIri);
        $recordSetConfig->setIO($io);
        $recordSetConfig->setImportJob($importJob);
        $result = $recordSetConfig->importFromFile($options, $key, $tmpDirectory, $tokenType);

        if (!$result) {
            $io->error('Record set import failed');
            return Command::FAILURE;
        }

        $io->success('Record set import was successful.');
        return Command::SUCCESS;
    }
}
