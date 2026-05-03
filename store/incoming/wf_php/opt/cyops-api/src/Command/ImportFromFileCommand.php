<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Command;

use Ramsey\Uuid\Uuid;
use App\Entity\Core\File;
use App\Entity\Core\PgFile;
use App\Entity\Core\ImportJob;
use App\Constants\AppConstants;
use App\Entity\Authorization\Team;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputOption;
use Symfony\Component\Console\Style\SymfonyStyle;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Output\OutputInterface;

class ImportFromFileCommand extends Command
{
    protected static $defaultName = 'app:import:from:file';

    protected $entityManager;

    public function __construct(EntityManagerInterface $entityManager)
    {
        $this->entityManager = $entityManager;
        parent::__construct();
    }

    protected function configure()
    {
        $this
            ->setDescription('Creates an import job and install default widgets into system')
            ->setDefinition([
                new InputOption(
                    'file-path',
                    'f',
                    InputOption::VALUE_REQUIRED,
                    'Path to exported JSON file to import.'
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
                )
            ]);
    }

    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        $io = new SymfonyStyle($input, $output);
        $rawToken = $input->getOption('user-token');
        $tokenType = $input->getOption('token-type');
        $filePath = $input->getOption('file-path');

        $jsonData = file_get_contents($filePath);

        $teamsRepo = $this->entityManager->getRepository(Team::class);
        $teams = $teamsRepo->findAll();

        $filename = 'exportData.json';
        $mimetype = 'application/json';
        $timestamp = new \DateTime('NOW', new \DateTimeZone('UTC'));

        $pgFile = new PgFile();
        /** @var AbstractFile $file */
        $pgFile->setFile(base64_encode($jsonData));
        $pgFile->setUuid(Uuid::uuid4()->toString());
        $this->entityManager->persist($pgFile);
        $this->entityManager->flush();

        $file = new File();
        $file->setFile($pgFile->getUuid());
        $file->setFilename($filename);
        $file->setMimeType($mimetype);
        $file->setUploadDate($timestamp);
        $file->setSize(strlen($jsonData));
        $file->setUuid(Uuid::uuid4()->toString());
        foreach ($teams as $team) {
            $file->addOwner($team);
        }
        $this->entityManager->persist($file);
        $this->entityManager->flush();

        $importJob = new ImportJob();
        $importJob->setFile(AppConstants::FILE_IRI.$file->getUuid());
        $importJob->setUuid(Uuid::uuid4()->toString());
        $this->entityManager->persist($importJob);
        $this->entityManager->flush();

        $tokenPart = sprintf('--user-token=%s --token-type=%s', $rawToken, $tokenType);

        $optionsCommand = sprintf('/usr/bin/php /opt/cyops-api/bin/console fortisoar:jobs:import --job-uuid=%s -o %s > /var/log/cyops/cyops-api/last_config_import.log 2>&1', $importJob->getUuid(), $tokenPart);
        exec($optionsCommand, $out, $errorCode);

        if (!$errorCode) {
            $runImportCommand = sprintf('/usr/bin/php /opt/cyops-api/bin/console fortisoar:jobs:import --job-uuid=%s %s -x', $importJob->getUuid(), $tokenPart);
            exec(sprintf('bash -c "exec nohup setsid %s >> /var/log/cyops/cyops-api/last_config_import.log 2>&1 &"', $runImportCommand));
        }

        $io->success('Widget Imported Successfully.');
        return Command::SUCCESS;
    }
}
