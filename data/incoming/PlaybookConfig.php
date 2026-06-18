<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Service\ConfigExportImport;

use stdClass;
use Ramsey\Uuid\Uuid;
use App\Entity\Core\Tag;
use App\Entity\Core\Image;
use App\Entity\Core\PgFile;
use Psr\Log\LoggerInterface;
use App\Entity\Core\Picklist;
use App\Constants\AppConstants;
use App\Service\UtilityService;
use App\Security\Voter\FsrVoter;
use App\Entity\Workflow\Workflow;
use App\Constants\ErrorConstants;
use App\Entity\Workflow\WorkflowVersion;
use Doctrine\ORM\EntityManagerInterface;
use App\Entity\Workflow\WorkflowStepType;
use ApiPlatform\Api\IriConverterInterface;
use App\Entity\Workflow\WorkflowCollection;
use App\Entity\Authorization\Team;
use App\Providers\PermissionsDictionaryBuilder;
use ApiPlatform\Core\Exception\ItemNotFoundException;
use App\Service\ConfigExportImport\PlaybookHelperConfig;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\Serializer\Normalizer\NormalizerInterface;
use Symfony\Component\Security\Core\Authentication\Token\Storage\TokenStorageInterface;

/**
 * Class PlaybookConfig
 * @package App\Service\ConfigExportImport
 */
class PlaybookConfig extends PortingConfig
{
    private const STEP_TYPES = [
        'MANUAL_INPUT' => 'fc04082a-d7dc-4299-96fb-6837b1baa0fe',
        'DECISION' => '12254cf5-5db7-4b1a-8cb1-3af081924b28'
    ];
    /** @var FsrVoter */
    private $fsrVoter;

    /** @var PlaybookHelperConfig */
    private $playbookHelperConfig;

    private $requiredMacros = [];

    private $utilityService;

    private const WORKFLOW_CONTEXT = '/api/3/contexts/Workflow';
    private const WORKFLOW_IRI = '/api/3/workflows/';
    private const WORKFLOW_STEP_IRI = '/api/3/workflow_steps/';
    private const WORKFLOW_STEP_TYPE_IRI = '/api/3/workflow_step_types/';
    private const WORKFLOW_ROUTE_IRI = '/api/3/workflow_routes/';
    private const WORKFLOW_GROUP_IRI = '/api/3/workflow_groups/';
    private const SCHEDULE_KEY = 'includeSchedules';
    private const GLOBAL_VARIABLE_KEY = 'includeGlobalVariables';
    private const VERSIONS_KEY = 'includeVersions';

    public function __construct(
        FsrVoter $fsrVoter,
        protected ImportOptionsGenerator $importOptionsGenerator,
        EntityManagerInterface $entityManager,
        NormalizerInterface $normalizer,
        TokenStorageInterface $tokenStorage,
        ContainerInterface $container,
        UtilityService $utilityService,
        protected LoggerInterface $logger,
        PlaybookHelperConfig $playbookHelperConfig,
        private IriConverterInterface $iriConverter
    ) {
        $this->fsrVoter = $fsrVoter;
        $this->importOptionsGenerator = $importOptionsGenerator;
        $this->utilityService = $utilityService;
        $this->playbookHelperConfig = $playbookHelperConfig;
        parent::__construct($entityManager, $normalizer, $tokenStorage, $container, $logger);
    }

    /**
     * @param array $allData
     * @param string $key
     * @return array
     */
    public function getImportOptions(array $allData, string $key, $tokenType)
    {
        $data = $allData[$key];
        if (
            !$this->fsrVoter->isGranted(PermissionsDictionaryBuilder::PERM_CRUD_UPDATE . '.workflows') ||
            !$this->fsrVoter->isGranted(PermissionsDictionaryBuilder::PERM_CRUD_CREATE . '.workflows') ||
            !$this->fsrVoter->isGranted(PermissionsDictionaryBuilder::PERM_CRUD_READ . '.workflows')
        ) {
            return [];
        }
        $options = [];
        if (array_key_exists('collections', $data) && count($data['collections']) > 0) {
            $subOptions = $this->playbookHelperConfig->generatePlaybookCollectionOptions($data['collections'], $this->importJob);
            $options['collections'] = [
                "include" => count($subOptions) > 0,
                "values" => $subOptions
            ];
        }
        if (array_key_exists('globalVariables', $data) && count($data['globalVariables']) > 0) {
            $subOptions = $this->generateGlobalVariableOptions($data['globalVariables'], $tokenType);
            $options['globalVariables'] = [
                "include" => count($subOptions) > 0,
                "values" => $subOptions
            ];
        }
        return $options;
    }

    /**
     * @param array $config
     * @return array
     */
    private function generateGlobalVariableOptions(array $dynamicVariables, $tokenType)
    {
        $existingDynamicVariables = $this->getGlobalVariables($tokenType);
        $existingDynamicVariableNames = array_column($existingDynamicVariables, 'name');
        $options = [];
        foreach ($dynamicVariables as $dynamicVariable) {
            $existing = in_array($dynamicVariable['name'], $existingDynamicVariableNames);
            $individualOptions = [];
            $individualOptions['name'] = $dynamicVariable['name'];
            $individualOptions['include'] = !$existing;
            $individualOptions['required'] = !$existing && in_array($dynamicVariable['name'], $this->requiredMacros);
            $individualOptions['exists'] = $existing;

            $options[] = $individualOptions;
        }
        return $options;
    }

    /**
     * Imports the config data using the specified options
     *
     * @param array $data
     * @param array $options
     * @param string $tokenType
     * @return mixed
     */
    public function import(array $data, array $options, $tokenType, $importedBy = [])
    {
        $tagsResult = true;
        if (array_key_exists('exported_tags', $data)) {
            $tagsResult = $this->importTags($data['exported_tags'], $tokenType);
        }
        $collectionResult = true;
        if (array_key_exists('collections', $options) && $options['collections']['include']) {
            $collectionResult = $this->importPlaybookCollections($data['collections'], $options['collections']['values'], $tokenType, $importedBy);
        }
        $globalVariableResult = true;
        if (array_key_exists('globalVariables', $options) && $options['globalVariables']['include']) {
            $globalVariableResult = $this->importGlobalVariables($data['globalVariables'], $options['globalVariables']['values'], $tokenType);
        } elseif (array_key_exists('globalVariables', $options) && array_key_exists('collections', $options) && $options['collections']['include']) {
            // Import required global variables from playbooks
            $requiredMacros = [];
            foreach ($options['collections']['values'] as $collection) {
                $requiredMacros = array_merge($requiredMacros, $collection['macros']);
            }
            $uniqueRequiredMacros = array_unique($requiredMacros);
            $requiredMacrosToImport = [];
            foreach ($options['globalVariables']['values'] as $globalVariable) {
                if (in_array($globalVariable['name'], $uniqueRequiredMacros)) {
                    $requiredMacrosToImport[] = $globalVariable;
                }
            }
            $globalVariableResult = $this->importGlobalVariables($data['globalVariables'], $requiredMacrosToImport, $tokenType);
        }
        return $collectionResult && $globalVariableResult && $tagsResult;
    }

    private function importTags($tags, $tokenType)
    {
        $repository = $this->loadRepository(Tag::class);
        $tagObjects = [];
        foreach ($tags as $tag) {
            $existing = $repository->findOneBy(['uuid' => $tag]);
            if ($existing) {
                continue;
            }
            $tagObjects[] = [
                'uuid' => $tag
            ];
        }
        if (!empty($tagObjects)) {
            $fullURI = sprintf('%s/api/3/bulkupsert/tags', $this->container->getParameter(AppConstants::CRUDHUB_PARAMETER_KEY));
            $body = [
                "__unique" => ['uuid'],
                "__replace" => false,
                "__data" => $tagObjects
            ];
            return $this->sendRequest($fullURI, 'post', $body, $tokenType);
        }
        return true;
    }

    /**
     * Returns an array of all Team UUIDs from the database.
     *
     * @return array
     */
    private function getExistingTeamUuids(): array
    {
        $qb = $this->entityManager->createQueryBuilder();
        $qb->select('t.uuid')
            ->from(Team::class, 't');
        $result = $qb->getQuery()->getArrayResult();
        return array_column($result, 'uuid');
    }

    /**
     * Checks if there is any private playbook in the given collection
     *
     * @param array $collection
     * @return bool
     */
    private function isPrivatePlaybookExists($collection): bool
    {
        foreach ($collection['workflows'] as $playbook) {
            if (array_key_exists('isPrivate', $playbook) && $playbook['isPrivate'] === true) {
                return true;
            }
        }
        return false;
    }

    /**
     * Imports playbook collections
     *
     * @param array $collections
     * @param array $collectionOptions
     * @return boolean
     */
    private function importPlaybookCollections(array $collections, array $collectionOptions, $tokenType, $importedBy = [])
    {
        $toAdd = [];
        $toAppend = [];
        $deleteUuids = [];
        $playbooksToDelete = [];
        $schedulesToImport = [];
        $uuidMap = [];
        $playbookRepository = $this->loadRepository(Workflow::class);
        $collectionRepository = $this->loadRepository(WorkflowCollection::class);
        $importJobType = $this->importJob ? $this->importJob->getType() : AppConstants::IMPORT_JOB_TYPES["IMPORT_WIZARD"];
        $playbookVersionsToAdd = [];
        $playbookVersionsToUpdate = [];
        $playbooksToUpdate = [];
        $existingTeams = [];
        $existingTeamsMap =[];
        $hasAnyPrivatePlaybook = false;

        try {
            $spOrigin = $this->iriConverter->getResourceFromIri(AppConstants::WORKFLOW_ORIGIN_IRI_MAP['SOLUTION_PACK'], ['resource_class' => Picklist::class, 'fetch_data' => true]);
        } catch (ItemNotFoundException $infe) {
            $errorMessage = sprintf(ErrorConstants::FSR_CH_0000013, "Solution Pack");
            $this->logger->error($errorMessage);
            $spOrigin = null;
        }

        foreach ($collections as $collection) {
            $hasAnyPrivatePlaybook = $hasAnyPrivatePlaybook || $this->isPrivatePlaybookExists($collection);
        }
        if ($hasAnyPrivatePlaybook) {
            $existingTeams = $this->getExistingTeamUuids();
            $existingTeamsMap = array_flip($existingTeams);
        }

        foreach ($collectionOptions as $playbookCollectionOption) {
            if (!$playbookCollectionOption['include']) {
                // Do not merge skipped items
                continue;
            }
            foreach ($collections as $collectionKeyIndex => $collection) {
                $playbooksToRemoveFromCollection = [];
                if ($playbookCollectionOption['uuid'] == $collection['uuid']) {
                    $newPlaybooks = [];
                    $hasPrivatePlaybook = false;

                    // Check for any private playbook
                    $hasPrivatePlaybook = $hasAnyPrivatePlaybook && $this->isPrivatePlaybookExists($collection);

                    foreach ($collection['workflows'] as $playbookIndex => &$playbook) {
                        // Backward compatibility: set default values if keys are missing
                        if (!array_key_exists('isPrivate', $playbook)) {
                            $playbook['isPrivate'] = false;
                        }
                        if (!array_key_exists('owners', $playbook) || !is_array($playbook['owners'])) {
                            $playbook['owners'] = [];
                        }

                        if ($hasPrivatePlaybook && $playbook['isPrivate']) {
                            // Validate owners only if there is a private playbook
                            if (count($playbook['owners']) > 0) {
                                $validOwners = [];
                                foreach ($playbook['owners'] as $ownerUuid) {
                                    $ownerUuid = is_string($ownerUuid) && strpos($ownerUuid, '/') !== false
                                        ? basename($ownerUuid)
                                        : $ownerUuid;

                                    if (isset($existingTeamsMap[$ownerUuid])) {
                                        $validOwners[] = $ownerUuid;
                                    }
                                }
                                $playbook['owners'] = $validOwners;
                                if (count($validOwners) > 0) {
                                    $this->logger->info("At least one team found for playbook '{$playbook['name']}'. Importing as-is.");
                                } else {
                                    $playbook['isPrivate'] = false;
                                    $playbook['owners'] = [];
                                    $this->logger->warning("No valid team found for playbook '{$playbook['name']}'. Set Private and owners None on playbook.");
                                }
                            }
                        } else {
                            // If no private playbook, set all to public and owners empty
                            $playbook['isPrivate'] = false;
                            $playbook['owners'] = [];
                        }
                        $remove = false;
                        $playbook = $this->handleIsEditableAndPlaybookOrigin($playbook, $importJobType);
                        /** @var Workflow $existingPlaybook */
                        $existingPlaybookByUuid = $playbookRepository->find($playbook['uuid']);
                        if (!is_null($existingPlaybookByUuid)) {
                            $this->entityManager->refresh($existingPlaybookByUuid);
                        }
                        if ($existingPlaybookByUuid && ($existingPlaybookByUuid->getCollection()->getUuid() != $collection['uuid'] || $playbookCollectionOption['mergeType'] === 'rename')) {
                            // If a uuid already exists in a different collection, or if we are renaming the current collection, generate a new one
                            $this->logger->info("UUID already exists in a different collection, or if we are renaming the current collection");
                            $newUuid = Uuid::uuid4()->toString();
                            $uuidMap[$playbook['uuid']] = $newUuid;
                            $playbook['uuid'] = $newUuid;
                            // this is the only case where the step ids would also cause a conflict
                            $playbook = $this->fixStepUuids($playbook);
                        } elseif ($existingPlaybookByUuid && $existingPlaybookByUuid->getCollection()->getUuid() == $collection['uuid']) {
                            if ($playbookCollectionOption['mergeType'] === 'merge_replace') {
                                if ($importJobType == AppConstants::IMPORT_JOB_TYPES["SOLUTION_PACK_IMPORT"]) {
                                    $this->handlePlaybookImportThroughSolutionPack($existingPlaybookByUuid, $playbook, $playbookVersionsToUpdate, $playbooksToRemoveFromCollection, $playbooksToUpdate, $playbooksToDelete, $spOrigin);
                                } else {
                                    // Replacing existing playbook when imported through import wizard
                                    // If we are replacing existing playbooks, we need to remove any found playbooks by UUID in the same collection
                                    $playbooksToDelete[] = $existingPlaybookByUuid->getUuid();
                                }
                            } elseif ($playbookCollectionOption['mergeType'] === 'merge_append') {
                                // If we are appending, we skip any existing playbooks
                                $remove = true;
                            }
                        } elseif (!$existingPlaybookByUuid && $importJobType == AppConstants::IMPORT_JOB_TYPES["SOLUTION_PACK_IMPORT"] && $playbook['isEditable']) {
                            // Creating base version for playbooks with 'isEditable=true' while adding playbooks through SP for first time
                            $playbookVersionsToAdd[] = ["newPlaybook" => $playbook];
                        }

                        if ($playbookCollectionOption['exists']) {
                            $existingPlaybookByName = $playbookRepository->findOneBy(['name' => $playbook['name'], 'collection' => $playbookCollectionOption['existing_uuid']]);
                            if ($existingPlaybookByName) {
                                if ($playbookCollectionOption['mergeType'] === 'merge_replace') {
                                    if ($importJobType == AppConstants::IMPORT_JOB_TYPES["SOLUTION_PACK_IMPORT"]) {
                                        $this->handlePlaybookImportThroughSolutionPack($existingPlaybookByName, $playbook, $playbookVersionsToUpdate, $playbooksToRemoveFromCollection, $playbooksToUpdate, $playbooksToDelete, $spOrigin);
                                    } else {
                                        // If we are replacing existing playbooks, we need to remove any found playbooks by UUID in the same collection
                                        $playbooksToDelete[] = $existingPlaybookByName->getUuid();
                                    }
                                } elseif ($playbookCollectionOption['mergeType'] === 'merge_append') {
                                    // If we are appending, we just need to add the playbook
                                    $remove = true;
                                }
                            }
                        }
                        unset($playbook['collection']);

                        # Incoming JSON
                        $playbook['lastModifyDate'] = time();

                        if (array_key_exists('schedules', $playbook) && $playbookCollectionOption['includeSchedules']) {
                            foreach ($playbook['schedules'] as $schedule) {
                                $schedule['kwargs']['wf_iri'] = sprintf('/api/3/workflows/%s', $playbook['uuid']);
                                $schedulesToImport[] = $schedule;
                            }
                        }

                        if (!$remove) {
                            $playbook['importedBy'] = array_key_exists("importedBy", $playbook) && $playbook['importedBy'] ? array_merge($playbook['importedBy'], $importedBy) : $importedBy;
                            $newPlaybooks[] = $playbook;
                        }
                    }
                    $collection['workflows'] = $newPlaybooks;
                    $collection = $this->importCollectionImage($collection);
                    if (!empty($playbooksToRemoveFromCollection)) {
                        // Removing playbooks from coming collection which exists in system and for which 'isEditable=true' in system
                        $collectionWorkflows = [];
                        foreach ($collection['workflows'] as $playbook) {
                            if (!in_array($playbook['uuid'], array_unique($playbooksToRemoveFromCollection))) {
                                $collectionWorkflows[] = $playbook;
                            }
                        }
                        $collection['workflows'] = $collectionWorkflows;
                    }
                    if ($playbookCollectionOption['exists'] && empty($collections[$collectionKeyIndex]['workflows'])) {
                        // If collection exists in system and playbooks from collection are 'isEditable=true' in system as well as in coming collection are all 'isEditable=true',
                        // then we update version of those playbooks with coming change and remove these playbooks from coming collection.
                        // So, coming collection becomes empty. Removing such collection from array to reduce further number of iterations.
                        unset($collections[$collectionKeyIndex]);
                        break;
                    }
                    if (!$playbookCollectionOption['exists_uuid'] && !$playbookCollectionOption['exists_name']) {
                        $collection['importedBy'] = array_key_exists("importedBy", $collection) && $collection['importedBy'] ? array_merge($collection['importedBy'], $importedBy) : $importedBy;
                        $toAdd[] = $collection;
                        break;
                    }
                    if ($playbookCollectionOption['mergeType'] === 'rename') {
                        $number = 1;
                        while ($collectionRepository->findOneBy(['name' => $collection['name'] . ' (' . $number . ')'])) {
                            $number++;
                        }
                        $collection['name'] = $collection['name'] . ' (' . $number . ')';
                        if ($playbookCollectionOption['exists_uuid']) {
                            unset($collection['uuid']);
                        }
                        $collection['importedBy'] =  array_key_exists('importedBy', $collection) ? array_merge($collection['importedBy'], $importedBy) : $importedBy;
                        $toAdd[] = $collection;
                        break;
                    } elseif ($playbookCollectionOption['mergeType'] === 'replace') {
                        $deleteUuids[] = $playbookCollectionOption['existing_uuid'];
                        $toAdd[] = $collection;
                    } elseif (in_array($playbookCollectionOption['mergeType'], ['merge_replace', 'merge_append'])) {
                        // UI Name (Merge Replace Existing Playbook)
                        $collection['uuid'] = $playbookCollectionOption['existing_uuid'];
                        $collection['importedBy'] = array_key_exists('importedBy', $collection) ? array_merge($collection['importedBy'], $importedBy) : $importedBy;
                        $toAppend[] = $collection;
                    }
                    break;
                }
            }
            // Fix reference playbooks
            foreach ($toAdd as $collectionIndex => $collection) {
                foreach ($collection['workflows'] as $playbookIndex => $playbook) {
                    $toAdd[$collectionIndex]['workflows'][$playbookIndex] = $this->fixReferencePlaybookUuids($playbook, $uuidMap);
                }
            }
            foreach ($toAppend as $collectionIndex => $collection) {
                foreach ($collection['workflows'] as $playbookIndex => $playbook) {
                    $toAppend[$collectionIndex]['workflows'][$playbookIndex] = $this->fixReferencePlaybookUuids($playbook, $uuidMap);
                }
            }
        }
        $results = [];
        if (!empty($deleteUuids)) {
            $fullURI = sprintf('%s/api/3/delete-with-query/workflow_collections?$showDeleted=true', $this->container->getParameter(AppConstants::CRUDHUB_PARAMETER_KEY));
            $filterObj = new stdClass();
            $filterObj->{'field'} = "uuid";
            $filterObj->{'operator'} = "in";
            $filterObj->{'value'} = array_unique($deleteUuids);
            $filterObj->{'type'} = "primitive";
            $body = [$filterObj];

            $data = new stdClass();
            $data->{'logic'} = 'AND';
            $data->{'filters'} = $body;
            $this->sendRequest($fullURI, 'delete', $data, $tokenType);
        }
        if (!empty($playbooksToDelete)) {
            $filterObj = new stdClass();
            $filterObj->{'field'} = "uuid";
            $filterObj->{'operator'} = "in";
            $filterObj->{'value'} = array_unique($playbooksToDelete);
            $filterObj->{'type'} = "primitive";
            $body = [$filterObj];

            $data = new stdClass();
            $data->{'logic'} = 'AND';
            $data->{'filters'} = $body;

            $fullURI = sprintf('%s/api/3/delete-with-query/workflows?$showDeleted=true', $this->container->getParameter(AppConstants::CRUDHUB_PARAMETER_KEY));
            $this->sendRequest($fullURI, 'delete', $data, $tokenType);
        }
        if (!empty($playbooksToUpdate)) {
            foreach ($playbooksToUpdate as $playbookToUpdate) {
                $this->entityManager->persist($playbookToUpdate);
            }
            $this->entityManager->flush();
        }
        foreach ($toAdd as $item) {
            $fullURI = sprintf('%s/api/3/workflow_collections', $this->container->getParameter(AppConstants::CRUDHUB_PARAMETER_KEY));
            $result = $this->sendRequest($fullURI, 'post', $item, $tokenType);
            $results[] = $result;
        }
        foreach ($toAppend as $collection) {
            foreach ($collection['workflows'] as $playbook) {
                $playbook['collection'] = sprintf('/api/3/workflow_collections/%s', $collection['uuid']);
                $fullURI = sprintf('%s/api/3/workflows', $this->container->getParameter(AppConstants::CRUDHUB_PARAMETER_KEY));
                $result = $this->sendRequest($fullURI, 'post', $playbook, $tokenType);
                $results[] = $result;
            }
            unset($collection['workflows']);
            $fullURI = sprintf('%s/api/3/workflow_collections/%s', $this->container->getParameter(AppConstants::CRUDHUB_PARAMETER_KEY), $collection['uuid']);
            $result = $this->sendRequest($fullURI, 'put', $collection, $tokenType);
            $results[] = $result;
        }
        if (!empty($playbookVersionsToAdd)) {
            foreach ($playbookVersionsToAdd as $versionToAdd) {
                $newPlaybook = $versionToAdd["newPlaybook"];
                $playbookByUuid = $playbookRepository->findOneBy(['uuid' => $newPlaybook['uuid']]);
                $playbookVersionToAdd = $this->createPlaybookVersion($playbookByUuid, $newPlaybook);
                $this->entityManager->persist($playbookVersionToAdd);
            }
            $this->entityManager->flush();
        }
        if (!empty($playbookVersionsToUpdate)) {
            $workflowVersionRepo = $this->entityManager->getRepository(WorkflowVersion::class);
            foreach ($playbookVersionsToUpdate as $key => $versionToUpdate) {
                $newPlaybook = $versionToUpdate["newPlaybook"];
                $existingPlaybookObject = $versionToUpdate["existingPlaybookObject"];
                $workflowUuid = $existingPlaybookObject->getUuid();
                $existingVersion = $workflowVersionRepo->findOneBy(["workflow" => $workflowUuid, "note" => AppConstants::WORKFLOW_VERSION_NAME]);
                if ($existingVersion) {
                    // If base version of existing playbook is present, update it
                    $this->fixNewPlaybookVersion($existingPlaybookObject, $newPlaybook);
                    $json_encoded = json_encode($newPlaybook);
                    $existingVersion->setJson($json_encoded);
                    $this->entityManager->persist($existingVersion);
                } else {
                    // If base version of existing playbook is not present, create one
                    $versionToAdd = $this->createPlaybookVersion($versionToUpdate["existingPlaybookObject"], $versionToUpdate["newPlaybook"]);
                    $this->entityManager->persist($versionToAdd);
                }
            }
            $this->entityManager->flush();
        }
        foreach ($schedulesToImport as $schedule) {
            $this->saveSchedule($schedule, $tokenType);
        }
        if (in_array(false, $results)) {
            return false;
        }
        return true;
    }

    private function handleIsEditableAndPlaybookOrigin($playbook, $importJobType)
    {
        // If isEditable is not present in coming playbook then set 'isEditable=false' if importJob type is 'Solution Import' else set 'isEditable=true'
        if (!array_key_exists('isEditable', $playbook)) {
            $playbook["isEditable"] = true;
            if ($importJobType == AppConstants::IMPORT_JOB_TYPES["SOLUTION_PACK_IMPORT"]) {
                $playbook["isEditable"] = false;
            }
        }

        // If playbookOrigin is present in coming playbook then keep as it is else make playbookOrigin='Custom'
        $playbookOrigin = $playbook["playbookOrigin"] ?? AppConstants::WORKFLOW_ORIGIN_IRI_MAP["CUSTOM"];
        // If importJob type is 'Solution Import' then playbookOrigin='Solution Pack'
        $playbook["playbookOrigin"] = $importJobType == AppConstants::IMPORT_JOB_TYPES["SOLUTION_PACK_IMPORT"] ? AppConstants::WORKFLOW_ORIGIN_IRI_MAP["SOLUTION_PACK"] : $playbookOrigin;
        return $playbook;
    }

    private function createPlaybookVersion($existingPlaybookObject, $newPlaybook)
    {
        $playbookVersion = new WorkflowVersion();
        $playbookVersion->setNote(AppConstants::WORKFLOW_VERSION_NAME);
        $playbookVersion->setWorkflow($existingPlaybookObject);
        $this->fixNewPlaybookVersion($existingPlaybookObject, $newPlaybook);
        $json_encoded = json_encode($newPlaybook);
        $playbookVersion->setJson($json_encoded);
        $playbookVersion->setCreateUser($existingPlaybookObject->getCreateUser());
        $playbookVersion->setModifyUser($existingPlaybookObject->getModifyUser());
        return $playbookVersion;
    }

    private function handlePlaybookImportThroughSolutionPack($existingPlaybookObject, &$newPlaybook, &$playbookVersionsToUpdate, &$playbooksToRemoveFromCollection, &$playbooksToUpdate, &$playbooksToDelete, $spOrigin = null)
    {
        $isEditable = $existingPlaybookObject->getIsEditable(); // This is existing value in database.
        $existingPlaybookOriginUuid = $existingPlaybookObject->getPlaybookOrigin()->getUuid(); // This too from database
        $workflowUuid = $newPlaybook['uuid']; // Incoming JSON uuid value

        // This will ensure there are no duplicate entries in playbookVersionsToUpdate
        if (array_key_exists($workflowUuid, $playbookVersionsToUpdate)) {
            return;
        }

        // Retaining value of 'isActive' what is in db
        // If 'isActive=false' in system but 'isActive=true' in zip then this will make playbook active if it got replaced.
        // Also, if 'isActive=true' in system but 'isActive=false' in zip then this will make playbook inactive if it got replaced.
        $newPlaybook['isActive'] = $existingPlaybookObject->getIsActive();

        if ($isEditable && $newPlaybook['isEditable']) {
            // 'isEditable=true' for playbook in system and 'isEditable=true' for incoming playbook
            // Update playbook version with new changes
            $playbookVersionsToUpdate[$workflowUuid] = ["existingPlaybookObject" => $existingPlaybookObject, "newPlaybook" => $newPlaybook];
            $playbooksToRemoveFromCollection[] = $workflowUuid;

            // Updating playbookOrigin of playbooks which are imported through SP but their playbookOrigin is Custom in db (Scenario:upgrade from 7.6.0 to 7.6.1)
            // To Do: As this will happen during upgrade from 7.6.0 to 7.6.1, following lines can be removed in 7.6.2
            if (!is_null($spOrigin)) {
                $existingPlaybookObject->setPlaybookOrigin($spOrigin);
                $playbooksToUpdate[] = $existingPlaybookObject;
            }
        } elseif (AppConstants::PICKLIST_IRI . $existingPlaybookOriginUuid == AppConstants::WORKFLOW_ORIGIN_IRI_MAP['SOLUTION_PACK'] && $isEditable && !$newPlaybook['isEditable']) {
            // If playbook origin='Solution Pack', isEditable=true for a playbook in system and isEditable=false for incoming playbook
            // Creating version for new changes in playbook.
            $newPlaybook['isEditable'] = $isEditable;
            $playbookVersionsToUpdate[$workflowUuid] = ["existingPlaybookObject" => $existingPlaybookObject, "newPlaybook" => $newPlaybook];
            $playbooksToRemoveFromCollection[] = $workflowUuid;
        } else {
            // 'isEditable=false' for playbook in system and 'isEditable=false' for incoming playbook OR
            // 'isEditable=false' for playbook in system but 'isEditable=true' for incoming playbook
            // 'isEditable=true' for playbook in system but 'isEditable=false' for incoming playbook
            // Replace playbook in system
            $playbooksToDelete[] = $existingPlaybookObject->getUuid();
            // 'isEditable=false' for playbook in system but 'isEditable=true' for incoming playbook, create version
            if (!$isEditable && $newPlaybook['isEditable']) {
                // If version is present it will update(if isEditable is set as false from DB), if not present then will create one
                $playbookVersionsToUpdate[$workflowUuid] = ["existingPlaybookObject" => $existingPlaybookObject, "newPlaybook" => $newPlaybook];
            }
        }
    }

    private function fixNewPlaybookVersion($existingPlaybookObject, &$newPlaybook)
    {
        $newPlaybook['@context'] = self::WORKFLOW_CONTEXT;
        $newPlaybook['@id'] = self::WORKFLOW_IRI . $newPlaybook['uuid'];
        $newPlaybook['importedBy'] = $existingPlaybookObject->getImportedBy();

        if ($newPlaybook['steps']) {
            foreach ($newPlaybook['steps'] as $key => $newPlaybookStep) {
                $newPlaybook['steps'][$key]['@id'] = self::WORKFLOW_STEP_IRI . $newPlaybookStep['uuid'];
                $stepTypeIri = str_starts_with($newPlaybookStep['stepType'], self::WORKFLOW_STEP_TYPE_IRI) ? $newPlaybookStep['stepType'] : self::WORKFLOW_STEP_TYPE_IRI . $newPlaybookStep['stepType'];
                $stepType = $this->getResourceFromIRI([$stepTypeIri], WorkflowStepType::class, true, true);
                if (array_key_exists('parent', $stepType[0]) && $stepType[0]['parent'] && str_starts_with($stepType[0]['parent'], self::WORKFLOW_STEP_TYPE_IRI)) {
                    $parent = $this->getResourceFromIRI([$stepType[0]['parent']], WorkflowStepType::class, true, true);
                    $stepType['parent'] = $parent[0];
                }
                $newPlaybook['steps'][$key]['stepType'] = $stepType[0];
                $newPlaybook['steps'][$key]['htmlEncodedName'] = $newPlaybookStep['name'];
                $newPlaybook['steps'][$key]['htmlEncodedDescription'] = null;
            }
        }

        if ($newPlaybook['routes']) {
            foreach ($newPlaybook['routes'] as $key => $newPlaybookRoute) {
                $newPlaybook['routes'][$key]['@id'] = self::WORKFLOW_ROUTE_IRI . $newPlaybookRoute['uuid'];
            }
        }

        if ($newPlaybook['groups']) {
            foreach ($newPlaybook['groups'] as $key => $newPlaybookGroup) {
                $newPlaybook['groups'][$key]['@id'] = self::WORKFLOW_GROUP_IRI . $newPlaybookGroup['uuid'];
            }
        }
    }

    private function importCollectionImage($collection)
    {
        $imageRepository = $this->entityManager->getRepository(Image::class);
        if ($collection['image'] && $collection['image_file']) {
            $image = $imageRepository->findOneBy(['uuid' => $collection['image']['uuid']]);
            if (!$image) {
                $image = new Image();
                $image->setUuid($collection['image']['uuid']);
                $image->setId($collection['image']['uuid']);
            }

            $image->setFilename($collection['image']['filename']);
            $image->setMimeType($collection['image']['mimeType']);
            $image->setSize($collection['image']['size']);

            $entityManager = $this->container->get('doctrine')->getManagerForClass(PgFile::class);
            $pgFile = null;
            if ($image->getFile()) {
                $pgFile = $entityManager->find(PgFile::class, $image->getFile());
            }
            if (!$pgFile) {
                $pgFile = new PgFile();
            }
            $pgFile->setFile($collection['image_file']);
            $entityManager->persist($pgFile);
            $image->setFile($pgFile->getUuid());
            $this->entityManager->persist($image);
            $this->entityManager->flush();
        }
        if (is_array($collection['image'])) {
            $collection['image'] = '/api/3/images/' . $collection['image']['uuid'];
        }
        return $collection;
    }

    private function fixReferencePlaybookUuids(array $playbook, array $uuidMap)
    {
        foreach ($playbook['steps'] as $index => $step) {
            if (array_key_exists('arguments', $step) && array_key_exists('workflowReference', $step['arguments'])) {
                $referenceUuid = str_replace('/api/3/workflows/', '', $step['arguments']['workflowReference']);
                if (array_key_exists($referenceUuid, $uuidMap)) {
                    $playbook['steps'][$index]['arguments']['workflowReference'] = sprintf('/api/3/workflows/%s', $uuidMap[$referenceUuid]);
                }
            }
        }
        return $playbook;
    }

    /**
     * Replaces the uuids for all playbook steps and points the routes to the new steps
     *
     * @param array $playbook
     * @return array
     */
    private function fixStepUuids(array $playbook)
    {
        $uuidMapping = [];
        $uuidGroupMapping = [];
        // First generate the new uuids and keep track using $uuidMapping
        $steps = [];
        foreach ($playbook['steps'] as $step) {
            $newUuid = Uuid::uuid4()->toString();
            $uuidMapping[$step['uuid']] = $newUuid;
            $step['uuid'] = $newUuid;
            $steps[] = $step;
        }
        $playbook['steps'] = $steps;

        $groups = [];
        foreach ($playbook['groups'] as $group) {
            $newUuid = Uuid::uuid4()->toString();
            $uuidGroupMapping[$group['uuid']] = $newUuid;
            $group['uuid'] = $newUuid;
            $groups[] = $group;
        }
        $playbook['groups'] = $groups;

        // Next, find all step references and replace them
        if ($playbook['triggerStep']) {
            $playbook['triggerStep'] = self::WORKFLOW_STEP_IRI . $uuidMapping[self::getUuidFromIri($playbook['triggerStep'])];
        }
        $routes = [];
        foreach ($playbook['routes'] as $route) {
            $route['uuid'] = Uuid::uuid4()->toString();
            $route['targetStep'] = self::WORKFLOW_STEP_IRI . $uuidMapping[self::getUuidFromIri($route['targetStep'])];
            $route['sourceStep'] = self::WORKFLOW_STEP_IRI . $uuidMapping[self::getUuidFromIri($route['sourceStep'])];
            $routes[] = $route;
        }
        $playbook['routes'] = $routes;
        $steps = [];
        foreach ($playbook['steps'] as $step) {
            if (array_key_exists('group', $step) && $step['group']) {
                $step['group'] = self::WORKFLOW_GROUP_IRI . $uuidGroupMapping[self::getUuidFromIri($step['group'])];
            }
            $stepTypeUuid = self::getUuidFromIri($step['stepType']);
            if ($stepTypeUuid == self::STEP_TYPES['MANUAL_INPUT']) {
                if (array_key_exists('timeout', $step['arguments']) && array_key_exists('step_iri', $step['arguments']['timeout'])) {
                    $step['arguments']['timeout']['step_iri'] = self::WORKFLOW_STEP_IRI . $uuidMapping[self::getUuidFromIri($step['arguments']['timeout']['step_iri'])];
                }
                $options = [];
                foreach ($step['arguments']['response_mapping']['options'] as $responseMappingOption) {
                    $responseMappingOption['step_iri'] = self::WORKFLOW_STEP_IRI . $uuidMapping[self::getUuidFromIri($responseMappingOption['step_iri'])];
                    $options[] = $responseMappingOption;
                }
                $step['arguments']['response_mapping']['options'] = $options;
            } elseif ($stepTypeUuid == self::STEP_TYPES['DECISION']) {
                $conditions = [];
                foreach ($step['arguments']['conditions'] as $condition) {
                    $condition['step_iri'] = self::WORKFLOW_STEP_IRI . $uuidMapping[self::getUuidFromIri($condition['step_iri'])];
                    $conditions[] = $condition;
                }
                $step['arguments']['conditions'] = $conditions;
            }
            $steps[] = $step;
        }
        $playbook['steps'] = $steps;
        return $playbook;
    }

    private function importGlobalVariables(array $globalVariables, array $globalVariableOptions, $tokenType)
    {
        $toAdd = [];
        foreach ($globalVariableOptions as $globalVariableOption) {
            if (!$globalVariableOption['include']) {
                // Do not merge skipped items
                continue;
            }
            foreach ($globalVariables as $globalVariable) {
                if ($globalVariableOption['name'] == $globalVariable['name']) {
                    $toAdd[] = $globalVariable;
                    break;
                }
            }
        }
        $results = [];
        foreach ($toAdd as $item) {
            $token = $this->getTokenFromStorage();
            if ($token) {
                $workflowMacroEndpoint = '/api/wf/api/dynamic-variable/';
                $uri = $this->container->getParameter(AppConstants::CRUDHUB_PARAMETER_KEY) . $workflowMacroEndpoint;
                $results[] = $this->sendRequest($uri, 'post', $item, $tokenType);
            } else {
                $workflowMacroEndpoint = '/api/dynamic-variable/';
                $uri = $this->container->getParameter('workflow.uri') . $workflowMacroEndpoint;
                $results[] = $this->sealabRequest($uri, 'post', $item, $tokenType);
            }
        }

        if (in_array(false, $results)) {
            return false;
        }
        return true;
    }

    /**
     * Exports the config using the specified options
     *
     * @param array $options
     * @return array
     */
    public function export(array $options, $tokenType = 'JWT')
    {
        if (!$this->fsrVoter->isGranted(PermissionsDictionaryBuilder::PERM_CRUD_READ . '.workflows')) {
            return [];
        }
        $usedMacros = [];
        if (array_key_exists('collections', $options)) {
            $uuids = $this->getUUIDsFromCollections($options['collections']);
            $data['collections'] = $this->getResourceFromIRI($uuids, WorkflowCollection::class, true);

            // Updating collection in case of include version selected for any collection
            $newCollections = [];
            $recordTags = [];
            foreach ($data['collections'] as $collection) {
                if (
                    $this->getValueOfKeyByCollectionUUID($options['collections'], $collection['uuid'], self::VERSIONS_KEY) ||
                    (array_key_exists('includeVersions', $options) && $options['includeVersions'])
                ) {
                    $iris = [];
                    foreach ($collection['workflows'] as $playbook) {
                        $iris[] = '/api/3/workflows/' . $playbook['uuid'];
                        foreach ($playbook['recordTags'] as $recordTag) {
                            $parts = explode('/', $recordTag);
                            $recordTags[] = end($parts);
                        }
                    }
                    $collection['workflows'] = $this->getResourceFromIRI($iris, Workflow::class, true, true, true);
                    $newCollections[] = $collection;
                    foreach ($collection['recordTags'] as $recordTag) {
                        $parts = explode('/', $recordTag);
                        $recordTags[] = end($parts);
                    }
                } else {
                    $newCollections[] = $collection;
                }
            }
            if (!empty($newCollections)) {
                $data['collections'] = $newCollections;
            }

            $recordTags = [];
            $newCollections = [];
            foreach ($data['collections'] as $collection) {
                foreach ($collection['recordTags'] as $recordTag) {
                    $parts = explode('/', $recordTag);
                    $recordTags[] = end($parts);
                }
                foreach ($collection['workflows'] as $index => $playbook) {
                    if (
                        $this->exportJob->getType() == AppConstants::IMPORT_EXPORT_JOB_TYPES["SOLUTION_PACK_EXPORT"] &&
                        $collection['workflows'][$index]['playbookOrigin'] == AppConstants::WORKFLOW_ORIGIN_IRI_MAP["CUSTOM"]
                    ) {
                        // Changing value of 'playbookOrigin' to 'Solution Pack' and 'isEditable=false' in following condition
                        // When playbook export is through Solution Pack and 'playbookOrigin=Custom'
                        // Only changing these values when custom created playbooks are exported through custom Solution Pack
                        $collection['workflows'][$index]['playbookOrigin'] = AppConstants::WORKFLOW_ORIGIN_IRI_MAP["SOLUTION_PACK"];
                        $collection['workflows'][$index]['isEditable'] = false;
                    }
                    foreach ($playbook['recordTags'] as $recordTag) {
                        $parts = explode('/', $recordTag);
                        $recordTags[] = end($parts);
                    }
                    foreach ($playbook['groups'] as $groupIndex => $group) {
                        if (array_key_exists('workflowSteps', $group)) {
                            unset($collection['workflows'][$index]['groups'][$groupIndex]['workflowSteps']);
                        }
                        if (array_key_exists('workflowRoutes', $group)) {
                            unset($collection['workflows'][$index]['groups'][$groupIndex]['workflowRoutes']);
                        }
                    }
                    foreach ($playbook['steps'] as $workflowStep) {
                        if (array_key_exists('stepType', $workflowStep) && $workflowStep['stepType'] === AppConstants::WORKFLOW_STEP_TYPES_IRI_MAP["WorkflowReference"] && array_key_exists('workflowReference', $workflowStep['arguments'])) {
                            $referencedWorkflowIris[] = $workflowStep['arguments']['workflowReference'];
                        }
                    }
                    if ($this->getValueOfKeyByCollectionUUID($options['collections'], $collection['uuid'], self::SCHEDULE_KEY)) {
                        $schedules = $this->loadSchedules($playbook['uuid'], $tokenType, 'playbook');
                        if (count($schedules) > 0) {
                            foreach ($schedules as $key => &$schedule) {
                                if (array_key_exists('id', $schedule)) {
                                    unset($schedule['id']);
                                }
                            }
                            $collection['workflows'][$index]['schedules'] = $schedules;
                        }
                    }
                }
                if ((array_key_exists('includeGlobalVariables', $options) && $options['includeGlobalVariables']) ||
                    $this->getValueOfKeyByCollectionUUID($options['collections'], $collection['uuid'], self::GLOBAL_VARIABLE_KEY)
                ) {
                    $usedMacros = array_merge($usedMacros, $this->playbookHelperConfig->getMacrosAndScheduleCountFromPlaybooks($collection['workflows'])['macros']);
                }
                $newCollections[$collection['uuid']] = $collection;
            }
            $referencedWorkflows = $this->getResourceFromIRI($referencedWorkflowIris, Workflow::class, true, true, true);
            $referencedWorkflowCollectionIris = [];
            foreach ($referencedWorkflows as $referencedWorkflow) {
                $collectionUuid = end(explode('/', $referencedWorkflow['collection']));
                if (!array_key_exists($collectionUuid, $newCollections)) {
                    $referencedWorkflowCollectionIris[] = $referencedWorkflow['collection'];
                }
            }
            $referencedWorkflowCollections = $this->getResourceFromIRI($referencedWorkflowCollectionIris, WorkflowCollection::class, true);
            foreach ($referencedWorkflowCollections as $collectionIndex => $referencedWorkflowCollection) {
                foreach ($referencedWorkflowCollection['workflows'] as $workflowIndex => $workflow) {
                    $workflowIri = sprintf('/api/3/workflows/%s', $workflow['uuid']);
                    if (!in_array($workflowIri, $referencedWorkflowIris)) {
                        unset($referencedWorkflowCollections[$collectionIndex]['workflows'][$workflowIndex]);
                    } else if (
                        $this->exportJob->getType() == AppConstants::IMPORT_EXPORT_JOB_TYPES["SOLUTION_PACK_EXPORT"] &&
                        $collection['workflows'][$index]['playbookOrigin'] == AppConstants::WORKFLOW_ORIGIN_IRI_MAP["CUSTOM"]
                    ) {
                        // Changing value of 'playbookOrigin' to 'Solution Pack' and 'isEditable=false' in following condition
                        // When playbook export is through Solution Pack and 'playbookOrigin=Custom'
                        // Only changing these values when custom created playbooks are exported through custom Solution Pack
                        $referencedWorkflowCollections[$collectionIndex]['workflows'][$workflowIndex]['playbookOrigin'] = AppConstants::WORKFLOW_ORIGIN_IRI_MAP["SOLUTION_PACK"];
                        $referencedWorkflowCollections[$collectionIndex]['workflows'][$workflowIndex]['isEditable'] = false;
                    }
                }
            }
            $data['collections'] = $referencedWorkflowCollections ? array_merge(array_values($newCollections), $referencedWorkflowCollections) : array_values($newCollections);
            sort($recordTags);
            $data['exported_tags'] = array_values(array_unique($recordTags));
        }
        if (!empty($usedMacros) || !empty($options['globalVariables'])) {
            $data['globalVariables'] = [];
            $existingDynamicVariables = $this->getGlobalVariables($tokenType);
            $macrosToImport = !empty($options['globalVariables']) && !empty($usedMacros) ? array_unique(array_merge($options['globalVariables'] ?? [], $usedMacros)) : (empty($options['globalVariables']) && !empty($usedMacros) ? array_unique($usedMacros) : array_unique($options['globalVariables']));
            foreach ($macrosToImport as $dynamicVariableName) {
                foreach ($existingDynamicVariables as $existingDynamicVariable) {
                    if ($existingDynamicVariable['name'] == $dynamicVariableName) {
                        unset($existingDynamicVariable['id']);
                        $data['globalVariables'][] = $existingDynamicVariable;
                        break;
                    }
                }
            }
        }

        return $data ?? null;
    }

    /**
     * Exports the config to a tmp file using the specified options
     *
     * @param array $options
     * @param string $type
     * @param string $tokenType
     * @return void
     */
    public function exportFile(array $options, $type, $tmpDirectory, $tokenType = 'JWT')
    {
        $collectionMetaData = [];
        $data = $this->export($options, $tokenType);
        if (!$data) {
            return $data;
        }
        $directory = $tmpDirectory . $type . '/';
        $filenames = [];
        foreach ($data['collections'] as $collection) {
            $collectionName = $this->cleanFileName($collection['name']);
            $collectionFolder = $directory . $collectionName . '/';
            foreach ($collection['workflows'] as $playbook) {
                $playbookName = $this->cleanFileName($playbook['name']);
                $playbookFilename = $collectionFolder . $playbookName . '.json';
                $this->writeToFile($playbookFilename, $playbook);
                $filenames[] = $playbookFilename;
            }
            unset($collection['workflows']);
            $collectionFilename = $collectionFolder . 'collection.metadata.json';
            if (array_key_exists('image', $collection) && $collection['image']) {
                $image = end($this->getResourceFromIRI([$collection['image']], Image::class));
                $imageRepository = $this->entityManager->getRepository(Image::class);
                $iriParts = explode('/', $collection['image']);
                $imageObject = $imageRepository->findOneBy(['uuid' => end($iriParts)]);
                if ($imageObject) {
                    $fileRepository = $this->entityManager->getRepository(PgFile::class);
                    $pgFile = $fileRepository->findOneBy(['uuid' => $imageObject->getFile()]);
                    if ($pgFile) {
                        $collection['image_file'] = stream_get_contents($pgFile->getFile());
                        unset($image['thumbnail']);
                        $collection['image'] = $image;
                    }
                }
            }
            $this->writeToFile($collectionFilename, $collection);
            $collectionMetaData[] = ['name' => $collectionName];
            $filenames[] = $collectionFilename;
        }
        $data['globalVariables'] = array_key_exists('globalVariables', $data) && !empty($data['globalVariables']) ? $data['globalVariables'] : [];
        if (!empty($data['globalVariables'])) {
            $globalVariableFilename = $directory . 'globalVariables.json';
            $this->writeToFile($globalVariableFilename, $data['globalVariables']);
            $filenames[] = $globalVariableFilename;
            $this->appendToFile($tmpDirectory . 'info.json', 'globalVariables', $data['globalVariables']);
        }
        if (!empty($data['exported_tags'])) {
            $exportedTagsFilename = $directory . 'tags.json';
            sort($data['exported_tags']);
            $this->writeToFile($exportedTagsFilename, $data['exported_tags']);
            $filenames[] = $exportedTagsFilename;
        }
        if (!empty($collectionMetaData)) {
            $this->appendToFile($tmpDirectory . 'info.json', $type, $collectionMetaData);
        }

        return $filenames;
    }

    /**
     * Generates import options from the tmp folder
     *
     * @param string $key
     * @param string $tmpDirectory
     * @param string $tokenType
     * @return array
     */
    public function getImportOptionsFromFile(string $key, string $tmpDirectory, $tokenType)
    {
        $data = $this->loadDataFromDirectory($key, $tmpDirectory);
        return $this->getImportOptions([$key => $data], $key, $tokenType);
    }

    /**
     * Imports from the tmp folder
     *
     * @param array $options
     * @param string $key
     * @param string $tmpDirectory
     * @param [type] $tokenType
     * @return void
     */
    public function importFromFile(array $options, string $key, string $tmpDirectory, $tokenType, $importedBy = [])
    {
        $data = $this->loadDataFromDirectory($key, $tmpDirectory);
        return $this->import($data, $options, $tokenType, $importedBy);
    }

    protected function loadDataFromDirectory(string $key, string $tmpDirectory)
    {
        $data = $this->playbookHelperConfig->loadDataFromDirectory($key, $tmpDirectory);
        return $data;
    }

    public function generateExportOptions(array $options, $tokenType = 'JWT')
    {
        $exportOption['collections'] = [];
        $exportOption['globalVariables'] = [];
        foreach ($options['collections']['values'] as $value) {
            array_push($exportOption['collections'], $value['existing_uuid']);
        }
        if (array_key_exists('globalVariables', $options) && array_key_exists('values', $options['globalVariables'])) {
            foreach ($options['globalVariables']['values'] as $value) {
                array_push($exportOption['globalVariables'], $value);
            }
        }
        return $exportOption;
    }

    public function generateInfoContent(array $options)
    {
        $content = [];
        $collectionMetaData = [];
        if (array_key_exists('collections', $options)) {
            $filter = ['uuid' => $this->getUUIDsFromCollections($options['collections'])];
            $entityRepo = $this->entityManager->getRepository(WorkflowCollection::class);
            $dataObj = $this->utilityService->getItemWithWhere($entityRepo, $filter);
            foreach ($dataObj as $collection) {
                $collectionName = $this->cleanFileName($collection->getName());
                $collectionMetaData[] = ["name" => $collectionName];
            }
            $content["playbooks"] = $collectionMetaData;
        }
        $content["globalVariables"] = ['TBD. Depends on the variables used in the selected playbooks at the time of the export'];
        return $content;
    }

    private function getValueOfKeyByCollectionUUID(array $collections, $uuid, $key)
    {
        $index = array_search($uuid, array_column($collections, 'value'));
        return is_int($index) && array_key_exists($key, $collections[$index]) ? $collections[$index][$key] : null;
    }

    private function getUUIDsFromCollections(array $collections)
    {
        return !empty($collections) && is_string($collections[0]) ? $collections :
            array_map(function ($collection) {
                return $collection['value'];
            }, $collections);
    }
}
