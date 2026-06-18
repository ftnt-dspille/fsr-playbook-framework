<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Service\ConfigExportImport;

use GuzzleHttp\Client;
use App\Entity\Core\ImportJob;
use App\Constants\AppConstants;
use Doctrine\ORM\EntityManagerInterface;
use App\Entity\Workflow\WorkflowCollection;
use GuzzleHttp\Psr7\Request as GuzzleRequest;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpKernel\Exception\BadRequestHttpException;
use Symfony\Component\Security\Core\Authentication\Token\Storage\TokenStorageInterface;


/**
 * Class PlaybookHelperConfig
 * @package App\Service\ConfigExportImport
 */
class PlaybookHelperConfig
{
    # Added finished with error as its valid state
    public const WORKFLOW_EXECUTION_STATUS = ['finished', 'finished with error', 'failed', 'terminated'];
    public const WORKFLOW_EXECUTION_FAILED_STATUS = ['failed', 'terminated'];
    public const COLLECTION_METADATA_JSON = 'collection.metadata.json';
    public const GLOBAL_VARS_MACRO_REGEX = '/(?>globalVars|macro)\.(\w+)/m';
    public const MACRO_REGEX = '/"macro"\s*:\s*"([^"]+)"/';

    /** @var EntityManagerInterface */
    protected $entityManager;

    /** @var TokenStorageInterface */
    protected $tokenStorage;
    protected $container;

    private $requiredMacros = [];

    public function __construct(
        EntityManagerInterface $entityManager,
        ContainerInterface $container,
        TokenStorageInterface $tokenStorage,
    ) {
        $this->entityManager = $entityManager;
        $this->container = $container;
        $this->tokenStorage = $tokenStorage;
    }

    public function loadDataFromDirectory(string $key, string $tmpDirectory)
    {
        $folderPath = $tmpDirectory . $key . '/';
        $items = [];
        $data = [];
        if (file_exists($folderPath)) {
            $items = scandir($folderPath);
        }
        $data['collections'] = [];

        foreach ($items as $item) {
            if ($item == 'globalVariables.json') {
                $fileData = file_get_contents($folderPath . $item);
                $jsonData = json_decode($fileData, true);
                $data['globalVariables'] = $jsonData;
            } elseif ($item == 'tags.json') {
                $fileData = file_get_contents($folderPath . $item);
                $jsonData = json_decode($fileData, true);
                $data['exported_tags'] = $jsonData;
            } elseif ($item == 'execution_list.json') {
                $executionListJsonPath = $folderPath . $item;
                if (file_exists($executionListJsonPath)) {
                    $fileData = file_get_contents($executionListJsonPath);
                    $jsonData = json_decode($fileData, true);
                    $data['executionList'] = array_key_exists('execution_sequence', $jsonData) ? $jsonData['execution_sequence'] : [];
                }
            } elseif (file_exists($folderPath . $item . '/' . PlaybookHelperConfig::COLLECTION_METADATA_JSON)) {
                // Folder

                $playbooks = scandir($folderPath . $item . '/');
                $collectionFolder = $folderPath . $item . '/';
                $collectionFileData = file_get_contents($collectionFolder . PlaybookHelperConfig::COLLECTION_METADATA_JSON);
                $collection = json_decode($collectionFileData, true);
                $collection['workflows'] = [];
                foreach ($playbooks as $subFile) {
                    if ($subFile != PlaybookHelperConfig::COLLECTION_METADATA_JSON && substr($subFile, -5) == '.json') {
                        $pbFileData = file_get_contents($collectionFolder . $subFile);
                        $collection['workflows'][] = json_decode($pbFileData, true);
                    }
                }
                $data['collections'][] = $collection;
            }
        }
        return $data;
    }

    protected function loadRepository($resourceClass)
    {
        if (array_key_exists('softdeleteable', $this->entityManager->getFilters()->getEnabledFilters())) {
            $this->entityManager->getFilters()->disable('softdeleteable');
        }
        return $this->entityManager->getRepository($resourceClass);
    }

    /**
     * @param array $config
     * @return array
     */
    public function generatePlaybookCollectionOptions(array $playbookCollections, ?ImportJob $importJob = null)
    {
        $repository = $this->loadRepository(WorkflowCollection::class);
        $options = [];
        foreach ($playbookCollections as $playbookCollection) {
            $existingByUuid = $repository->findOneBy(['uuid' => $playbookCollection['uuid']]);
            $existingByName = $repository->findOneBy(['name' => $playbookCollection['name']]);
            $individualOptions = [];
            $individualOptions['uuid'] = $playbookCollection['uuid'];
            $individualOptions['name'] = $playbookCollection['name'];
            $softDeleted = false;
            if (!is_null($existingByUuid)) {
                $softDeleted = !is_null($existingByUuid->getDeletedAt());
            } elseif (!is_null($existingByName)) {
                $softDeleted = !is_null($existingByName->getDeletedAt());
            }
            $individualOptions['softDeleted'] = $softDeleted;
            $individualOptions['include'] = true;
            $individualOptions['mergeType'] = 'merge_append';
            // for solution packs, replace is the default behavior
            if ($importJob && $importJob->getType() === 'SolutionPack Import') {
                $individualOptions['mergeType'] = 'merge_replace';
            }
            $individualOptions['exists_uuid'] = $existingByUuid ? true : false;
            $individualOptions['existing_uuid'] = $existingByName ? $existingByName->getUuid() : $playbookCollection['uuid'];
            $individualOptions['exists_name'] = $existingByName ? true : false;
            $individualOptions['exists'] = $individualOptions['exists_uuid'] || $individualOptions['exists_name'];
            $results = $this->getMacrosAndScheduleCountFromPlaybooks($playbookCollection['workflows']);
            $individualOptions['macros'] = $results['macros'];
            $individualOptions['schedulesCount'] = $results['schedulesCount'];
            $individualOptions['includeSchedules'] = $individualOptions['schedulesCount'] > 0 ? true : false;
            $playbookCount = 0;
            if ($existingByName) {
                $playbookCount = count($existingByName->getWorkflows());
            } elseif ($existingByUuid) {
                $playbookCount = count($existingByUuid->getWorkflows());
            }
            $individualOptions['oldPlaybookCount'] = $playbookCount;
            $individualOptions['newPlaybookCount'] = count($playbookCollection['workflows']);

            $this->requiredMacros = array_unique(array_merge($this->requiredMacros, $individualOptions['macros']));

            $options[] = $individualOptions;
        }
        return $options;
    }

    public function getMacrosAndScheduleCountFromPlaybooks($playbooks)
    {
        $macros = [];
        $schedulesCount = 0;
        foreach ($playbooks as $playbook) {
            $this->collectMacrosFromPlaybook($playbook, $macros);

            if ($playbook['versions'] && count($playbook['versions'])) {
                foreach ($playbook['versions'] as $version) {
                    $version = json_decode($version['json'], true);
                    $this->collectMacrosFromPlaybook($version, $macros);
                }
            }
            if (array_key_exists('schedules', $playbook)) {
                $schedulesCount += count($playbook['schedules']);
            }
        }
        return array('macros' => array_unique($macros), 'schedulesCount' => $schedulesCount);
    }

    private function collectMacrosFromPlaybook($playbook, &$macros)
    {
        if (array_key_exists('steps', $playbook)) {
            foreach ($playbook['steps'] as $step) {
                if (array_key_exists('arguments', $step)) {
                    $argsJson = json_encode($step['arguments']);
                    // In set variable step, when global variable is used  then arguments contains 'globalVars.<Global Variable>'
                    $globalVarsMatches = [];
                    preg_match_all(PlaybookHelperConfig::GLOBAL_VARS_MACRO_REGEX, $argsJson, $globalVarsMatches, PREG_PATTERN_ORDER, 0);
                    // In update global variable step, arguments contain value as 'macro':'<Global Variable>' under params
                    $macroMatches = [];
                    preg_match_all(PlaybookHelperConfig::MACRO_REGEX, $argsJson, $macroMatches, PREG_PATTERN_ORDER, 0);

                    $macros = array_merge($macros, $globalVarsMatches[1], $macroMatches[1]);
                }
            }
        }
    }

    /**
     * Executes playbook
     *
     * @param object $playbook
     * @return boolean
     */
    public function executePlaybook($playbook, $tokenType)
    {
        $playbookUuid = $playbook->getUuid();
        $body = [
            "request" => [
                "data" => [
                    "__uuid" => "$playbookUuid"
                ]
            ]
        ];
        $fullURI = sprintf('%s/api/triggers/1/notrigger/%s', $this->container->getParameter(AppConstants::CRUDHUB_PARAMETER_KEY), $playbookUuid);
        $response = $this->sendRequest($fullURI, 'post', $body, $tokenType);
        $taskId = "";
        if ($response) {
            $jsonResponse = json_decode($response, true);
            $taskId = array_key_exists('task_id', $jsonResponse) && $jsonResponse['task_id'] ? $jsonResponse['task_id'] : "";
        }
        return $taskId;
    }

    public function checkWorkflowExecutionStatus($taskId)
    {
        # status was declared inside if which is being returned.
        $status = 'incipient';
        $workflowLogListEndpoint = "/api/workflows/log_list/?format=json&limit=10&offset=0&ordering=-modified&page=1&task_id=$taskId&parent_wf__isnull=True";
        $uri = $this->container->getParameter('workflow.uri') . $workflowLogListEndpoint;
        $result = $this->sealabRequest($uri, 'post', []);
        if ($result) {
            $workflowData = is_array($result) && count($result) == 1 ? $result[0] : null;
            $status = array_key_exists('status', $workflowData) && $workflowData['status'] ? $workflowData['status'] : "";
        }
        return $status;
    }

    public function deleteCollection(string $collectionUuid, $tokenType)
    {
        $body = ["ids" => [$collectionUuid]];
        $fullURI = sprintf('%s/api/3/delete/workflow_collections?$hardDelete=true', $this->container->getParameter(AppConstants::CRUDHUB_PARAMETER_KEY));
        $result = $this->sendRequest($fullURI, 'delete', $body, $tokenType);
    }

    public function sendRequest($uri, $method, $data = null, $tokenType = 'JWT', $params = [])
    {
        $token = $this->tokenStorage->getToken();
        if ($token && $tokenType == 'JWT') {
            $client = new Client();
        } else {
            $client = $this->container->get("app.proxy.client.crudhub");
        }
        $headers = [
            "Content-type" => "application/json",
            "Authorization" => $token ? sprintf("Bearer %s", $token->getCredentials()) : null
        ];
        $request = new GuzzleRequest($method, $uri, $headers, $data ? json_encode($data) : null);
        $params = array_merge($params, ['verify' => false]);
        try {
            $response = $client->send($request, $params);
            $statusCode = $response->getStatusCode();
            if ($statusCode < 400) {
                //$jsonDecodeResponse = json_decode($response->getBody()->getContents(), true);
                return $response->getBody()->getContents();
            } else {
                throw new \Exception($uri . '\n' . $response->getBody());
            }
        } catch (BadRequestHttpException | \Exception $exception) {
            $errCode = $exception->getCode();
            if ($errCode == 403) {
                $iri = str_replace($this->container->getParameter(AppConstants::CRUDHUB_PARAMETER_KEY), '', $uri);
                $module = explode('/', $iri)[4];
                if ($module) {
                    throw new \Exception(sprintf('You do not have %s access on %s module', AppConstants::METHOD_MAP[$method], $module));
                } else {
                    $error = json_decode($exception->getResponse()->getBody(), true);
                    if (array_key_exists('Error', $error)) {
                        throw new \Exception($error['Error']);
                    }
                    throw new \Exception($exception->getMessage());
                }
            } elseif ($errCode == 404) {
                $iri = str_replace($this->container->getParameter(AppConstants::CRUDHUB_PARAMETER_KEY), '', $uri);
                $message = $data ? json_encode($data) : "{}";
                throw new \Exception(sprintf('The Requested Resource %s (%s) Does not exists ', $iri, $method));
            } elseif ($errCode == 409) {
                $message = json_decode($exception->getResponse()->getBody(), true);
                $message = $message['hydra:description'] ?? $exception->getMessage();
                throw new \Exception($message);
            }
            $message = $exception->getResponse() ? $exception->getResponse()->getBody() : $exception->getMessage();
            throw new \Exception(sprintf('%d: %s', $errCode, $message));
        }
    }

    public function sealabRequest($uri, $method, $data = null)
    {
        $headers = ["Content-type" => "application/json"];
        $workflowRequest = new GuzzleRequest($method, $uri, $headers, $data ? json_encode($data) : null);
        $client = $this->container->get("app.proxy.client.workflow");
        try {
            $response = $client->send($workflowRequest, ['verify' => false]);
            $statusCode = $response->getStatusCode();
            if ($statusCode < 400) {
                $jsonDecodeResponse = json_decode($response->getBody()->getContents(), true);
                return array_key_exists('hydra:member', $jsonDecodeResponse) ? $jsonDecodeResponse['hydra:member'] : $jsonDecodeResponse;
            } else {
                throw new \Exception($uri . '\n' . $response->getBody());
            }
        } catch (BadRequestHttpException | \Exception $exception) {
            $errVar = json_decode($exception->getResponse()->getBody()->read(2048), true);
            $errMsg['message'] = $errVar['Error'] ? isset($errVar['Error']) : $errVar['error'];
            $errCode = $exception->getCode();
            throw  new \Exception(sprintf('%d: %s', $errCode, $errMsg));
        }
    }

    public function mapWorkflowUuidObject($workflowObjectsArray)
    {
        $workflowUuidObjectMap = [];
        foreach ($workflowObjectsArray as $workflowObject) {
            $workflowUuidObjectMap[$workflowObject->getUuid()] = $workflowObject;
        }
        return $workflowUuidObjectMap;
    }
}
