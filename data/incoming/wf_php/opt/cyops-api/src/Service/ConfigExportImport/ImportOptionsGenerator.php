<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Service\ConfigExportImport;

use Psr\Log\LoggerInterface;
use App\Entity\Core\ImportJob;
use App\Constants\AppConstants;
use Psr\Container\ContainerInterface;
use Doctrine\ORM\EntityManagerInterface;
use App\Service\SolutionPackUtilityService;
use Symfony\Component\Console\Style\SymfonyStyle;
use Symfony\Component\HttpKernel\Exception\HttpException;

/**
 * Class ImportOptionsGenerator
 * @package App\Service\ConfigExportImport
 */
class ImportOptionsGenerator extends ConfigPorter
{
    /** @EntityManagerInterface */
    private $entityManager;

    private $utilityService;

    public function __construct(
        EntityManagerInterface $entityManager, 
        SolutionPackUtilityService $utilityService, 
        ContainerInterface $container,
        protected LoggerInterface $logger)
    {
        $this->entityManager = $entityManager;
        $this->utilityService = $utilityService;
        parent::__construct($container);
    }
    /**
     * Generates all options for import given the config object
     *
     * @param array $config
     * @return array
     */
    public function generate(array $fullConfig, ImportJob $importJob, SymfonyStyle $io, $tokenType)
    {
        $options = [];
        $increment = intval(90 / count($this->configTypes));
        foreach ($this->configTypes as $key => $service) {
            $config = array_key_exists($key, $fullConfig) ? $fullConfig[$key] : [];
            /** @var PortingConfig $portingConfig */
            $portingConfig = $this->container->get($service);
            $portingConfig->setIO($io);
            $portingConfig->setImportJob($importJob);
            $message = sprintf('Working on options for %s', $key);
            $portingConfig->addMessage($message);

            $importOptions = $config ? $portingConfig->getImportOptions($fullConfig, $key, $tokenType) : [];
            $importJob->setProgressPercent($importJob->getProgressPercent() + $increment);
            $this->entityManager->persist($importJob);
            $this->entityManager->flush();
            if (!empty($importOptions)) {
                $options[$key] = [
                    "include" => true,
                    "values" => $importOptions
                ];
            }
        }
        if (empty($options)) {
            throw new \Exception('No importable configurations were found in the JSON file.');
        }
        return $options;
    }

    /**
     * Same as generate, but uses a folder path which is created from the tar.gz file
     *
     * @param string $folderPath
     * @param ImportJob $importJob
     * @param [type] $tokenType
     * @return void
     */
    public function generateFromFolder(string $folderPath, ImportJob $importJob, SymfonyStyle $io,  $tokenType)
    {
        $options = [];
        $increment = intval(90 / count($this->configTypes));
        foreach ($this->configTypes as $key => $service) {
            try {
                /** @var PortingConfig $portingConfig */
                $portingConfig = $this->container->get($service);
                $portingConfig->setIO($io);
                $portingConfig->setImportJob($importJob);
                $message = sprintf('Working on options for %s', $key);
                $portingConfig->addMessage($message);

                $importOptions = $portingConfig->getImportOptionsFromFile($key, $folderPath, $tokenType);

                $importJob->setProgressPercent($importJob->getProgressPercent() + $increment);
                $this->entityManager->persist($importJob);
                $this->entityManager->flush();

                if (!empty($importOptions)) {
                    $options[$key] = [
                        "include" => true,
                        "values" => $importOptions
                    ];
                }
            } catch (HttpException | \Exception $e) {
                $this->logger->error($e->getMessage());
                $errorMessage = sprintf("Option generation failed for %s with the following error %s. Please check logs.", $key, $e->getMessage());
                $this->utilityService->updateImportJob($importJob, AppConstants::STATUS['ERROR'], null, null, $errorMessage);
                throw $e;
            }
        }
        if (empty($options)) {
            throw new \Exception('No importable configurations were found in the JSON file while generate from folder.');
        }
        return $options;
    }

    public function generateSolutiopackOptionFromFolder(string $folderPath,  $tokenType = 'JWT')
    {
        $options = [];
        $increment = intval(90 / count($this->configTypes));
        foreach ($this->configTypes as $key => $service) {

            /** @var PortingConfig $portingConfig */
            $portingConfig = $this->container->get($service);
            $importOptions = $portingConfig->getImportOptionsFromFile($key, $folderPath, $tokenType);
            if (!empty($importOptions)) {
                $options[$key] = [
                    "include" => true,
                    "values" => $importOptions
                ];
            }
        }
        if (empty($options)) {
            throw new \Exception('No importable configurations were found in the JSON file while solutionpack option generation.');
        }
        return $options;
    }
}
