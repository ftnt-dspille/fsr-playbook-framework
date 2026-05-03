<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Service\ConfigExportImport;

use App\Entity\Core\ImportJob;
use App\Constants\AppConstants;
use Psr\Container\ContainerInterface;
use Doctrine\ORM\EntityManagerInterface;
use ApiPlatform\Api\IriConverterInterface;
use App\Service\SolutionPackUtilityService;
use Symfony\Component\Console\Style\SymfonyStyle;
use Symfony\Component\HttpKernel\Exception\HttpException;
use Symfony\Component\Security\Core\Authentication\Token\Storage\TokenStorageInterface;

/**
 * Class ImportService
 */
class ImportService extends ConfigPorter
{

    protected $iriConverter;
    /** @var TokenStorageInterface */
    private $tokenStorage;
    private $entityManager;
    private $solutionPackUtilityService;


    public function __construct(ContainerInterface $container, TokenStorageInterface $tokenStorage, IriConverterInterface $iriConverter,  EntityManagerInterface $entityManager, SolutionPackUtilityService $solutionPackUtilityService)
    {
        $this->iriConverter = $iriConverter;
        $this->tokenStorage = $tokenStorage;
        $this->entityManager = $entityManager;
        $this->solutionPackUtilityService = $solutionPackUtilityService;
        parent::__construct($container);
    }

    /**
     * 
     *
     * @param array $config
     * @return array
     */
    public function importConfiguration(array $fullData, ImportJob $importJob, SymfonyStyle $io, $tokenType = 'JWT', $importedBy = [])
    {
        $options = $importJob->getOptions();
        foreach ($this->configTypes as $key => $service) {
            $data = array_key_exists($key, $fullData) ? $fullData[$key] : [];
            $individualOptions = array_key_exists($key, $options) ? $options[$key] : [];
            if (!$data || empty($data) || !$individualOptions || !$individualOptions['include']) {
                continue;
            }
            /** @var PortingConfig $portingConfig */
            $portingConfig = $this->container->get($service);
            $portingConfig->setIO($io);
            $portingConfig->setImportJob($importJob);
            $message = sprintf('Working on %s', $key);
            $portingConfig->addMessage($message);
            $this->solutionPackUtilityService->updateImportJob($importJob, null, null, null, null, $key);
            $success = $portingConfig->import($data, $individualOptions['values'], $tokenType, $importedBy);
            if (!$success) {
                return [
                    "success" => false
                ];
            }
            $message = sprintf('Done with %s', $key);
            $portingConfig->addMessage($message);
        }

        return [
            "success" => true
        ];
    }

    /**
     * Same as import, but uses a folder path which is created from the tar.gz file
     *
     * @param string $folderPath
     * @param ImportJob $importJob
     * @param [type] $tokenType
     * @return void
     */
    public function importConfigurationFromFolder(string $folderPath, ImportJob $importJob, SymfonyStyle $io, $tokenType = 'JWT', $importedBy = [])
    {
        $options = $importJob->getOptions();
        $currentCount = 0;
        $totalCount = count($this->configTypes) + 1; //1 for cache clear step
        foreach ($this->configTypes as $key => $service) {
            $individualOptions = array_key_exists($key, $options) ? $options[$key] : [];
            if (!$individualOptions || !$individualOptions['include']) {
                continue;
            }
            /** @var PortingConfig $portingConfig */
            $portingConfig = $this->container->get($service);
            $portingConfig->setIO($io);
            $progressPercent = (int) (($currentCount / $totalCount) * 100);
            $portingConfig->setImportJob($importJob);
            $message = sprintf('Working on %s', $key);
            $portingConfig->addMessage($message);
            $user = $importJob->getModifyUser();
            if( $user ){
                $userIri = $this->iriConverter->getIriFromResource($user);
                $portingConfig->setImportUser($userIri);
            }
            $this->solutionPackUtilityService->updateImportJob($importJob, "Importing " . $key, $progressPercent, null, null, $key);
            try {
                $success = $portingConfig->importFromFile($individualOptions['values'], $key, $folderPath, $tokenType, $importedBy);
            } catch (HttpException | \Exception $e) {
                $errorMessage = sprintf("Import failed for %s with the following error %s", $key, $e->getMessage());
                $this->updateImportJob($importJob, AppConstants::STATUS['ERROR'], 0, null, $errorMessage, null);
                throw $e;
            }
            if (!$success) {
                return [
                    "success" => false
                ];
            }
            $currentCount = $currentCount + 1;
            $message = sprintf('Done with %s', $key);
            $portingConfig->addMessage($message);
        }
        $this->updateImportJob($importJob, AppConstants::STATUS['IMPORT_COMPLETE'], 100, null, null, 'completed');
        // ToDo update solution pack status to installed and the installed flag= true
        return ["success" => true];
    }

    public function updateImportJob(ImportJob $importJob, $status = null, $progressPercent = null, $options = null, $errorMessage = null, $currentlyImporting = null)
    {

        if ($status !== null) {
            $importJob->setStatus($status);
        }
        if ($progressPercent !== null) {
            $importJob->setProgressPercent($progressPercent);
        }
        if ($errorMessage !== null) {
            $importJob->setErrorMessage($errorMessage);
        }
        if ($options !== null) {
            $importJob->setOptions($options);
        }
        if ($currentlyImporting !== null) {
            $importJob->setCurrentlyImporting($currentlyImporting);
        }
        $timestamp = new \DateTime('NOW', new \DateTimeZone('UTC'));
        $importJob->setModifyDate($timestamp);
        $this->entityManager->persist($importJob);
        $this->entityManager->flush();
    }


    public function exportOptionGenerationFromInputOptions($options, $fileExtractedPath = null, $tokenType = 'JWT')
    {
        $exportData = [];
        foreach ($this->configTypes as $key => $service) {
            /** @var PortingConfig $portingConfig */
            $portingConfig = $this->container->get($service);
            $portingConfig->setTmpFilePath($fileExtractedPath);
            if (!empty($options[$key])) {
                $exportData[$key] = $portingConfig->generateExportOptions($options[$key], $tokenType);
            } else {
                $exportData[$key] = [];
            }
        }
        return $exportData;
    }
}
