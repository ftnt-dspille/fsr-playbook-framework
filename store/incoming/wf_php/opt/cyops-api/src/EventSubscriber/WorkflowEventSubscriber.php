<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\EventSubscriber;

use App\Constants\AppConstants;
use App\Utility\FilterUtility;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpKernel\Event\ViewEvent;
use Symfony\Component\HttpKernel\KernelEvents;
use Symfony\Component\Serializer\SerializerInterface;
use App\Constants\Triggers;
use App\Service\WorkflowHelper;
use App\Entity\Base\BaseEntity;
use App\Entity\Workflow\Workflow;
use App\Service\MetadataHelper;
use App\Service\UtilityService;
use Psr\Log\LoggerInterface;
use Symfony\Component\DependencyInjection\ParameterBag\ParameterBagInterface;

class WorkflowEventSubscriber implements EventSubscriberInterface
{
    const FIELD_BASED_TRIGGER = 'fieldbasedtrigger';
    const RESOURCE_PARAM = 'resource';

    public static function getSubscribedEvents()
    {
        return [
            KernelEvents::VIEW => ['handleTriggerType', 13]
        ];
    }

    public function __construct(
        private WorkflowHelper $workflowHelper,
        private EntityManagerInterface $entityManager,
        private SerializerInterface $serializer,
        private MetadataHelper $metadataHelper,
        private ParameterBagInterface $parameters,
        private UtilityService $utilityService,
        protected LoggerInterface $logger,
        protected FilterUtility $filterUtility
    ) {
        $this->workflowHelper = $workflowHelper;
        $this->entityManager = $entityManager;
        $this->serializer = $serializer;
        $this->metadataHelper = $metadataHelper;
        $this->parameters = $parameters;
        $this->utilityService = $utilityService;
    }

    public function handleTriggerType(ViewEvent $event)
    {
        $triggerType = null;
        $request = $event->getRequest();
        $source = (bool) $request->get('$' . AppConstants::IS_REPLICATION_FLAG, false) ? AppConstants::SOURCE_REPLICATE: AppConstants::SOURCE_ORIGIN;
        $newData = $request->attributes->get('data');
        $oldData = $request->attributes->get('previous_data');
        $fsr_previous_data = $request->attributes->get('fsr_previous_data');
        $newDataSerialized = $event->getControllerResult();
        $method = $event->getRequest()->getMethod();
        $skipPlaybookExecution = $request->attributes->get(AppConstants::SKIP_PLAYBOOK_EXECUTION, false);

        if (Request::METHOD_GET == $method || $skipPlaybookExecution) {
            return;
        }

        if ($method == Request::METHOD_DELETE) {
            if (is_null($oldData) || $oldData instanceof Workflow) {
                return;
            }
        } else {
            if (is_null($newData) || !($newData instanceof BaseEntity) || ($newData instanceof Workflow)) {
                return;
            }
        }
        $subRequestType = $event->getRequest()->attributes->get('fsr_subrequest_type');
        if ($subRequestType == 'agnostic_bulk' || $subRequestType == 'import') {
            // type agnostic and import need not call workflow
            return;
        }
        $resourceClassName = is_null($newData) ? get_class($oldData) : get_class($newData);
        $triggerResource = $this->metadataHelper->getTypeFromClassName($resourceClassName);

        if (is_null($oldData) && Request::METHOD_POST == $method) {
            $triggerType = Triggers::POST_CREATE;
        } elseif ($oldData && Request::METHOD_DELETE != $method) {
            $triggerType = Triggers::POST_UPDATE;
        } elseif (Request::METHOD_DELETE == $method) {
            $triggerType = Triggers::POST_DELETE;
        }
        if (is_null($triggerType)) {
            return;
        }

        $owners = [];
        if (!is_null($newData) && method_exists($newData, 'getOwners') && $newData->getOwners() != null) {
            foreach ($newData->getOwners() as $owner) {
                array_push($owners, $owner->getUuid());
            }
        }

        $oldDataNormalized = $fsr_previous_data;

        $triggerOnReplicate = $this->parameters->has('execute_workflow_on_replicate_node') ? $this->parameters->get('execute_workflow_on_replicate_node'): true;

        /* @var  WorkflowRepository */
        $workflowRepository = $this->entityManager->getRepository(Workflow::class);
        $workflows = $workflowRepository->getWorkflowsForTriggerType($triggerType, $owners, $triggerResource, $source, $triggerOnReplicate);

        if (count($workflows) == 0) {
            return;
        }

        $newDataNormalized = null;
        if ($triggerType == Triggers::POST_CREATE || $triggerType == Triggers::POST_UPDATE) {
            $newDataNormalized = json_decode($newDataSerialized, true);
        } elseif ($triggerType == Triggers::POST_DELETE) {
            $newDataNormalized =  $oldDataNormalized;
        }

        $applicableWorkflows = [];
        foreach ($workflows as $workflow) {
            $triggerStep = $workflow->getTriggerStep();
            $arguments = $triggerStep->getArguments() ?? [];

            # TODO: needs to be handled for API trigger
            $triggerParameter = self::RESOURCE_PARAM;

            //Validate trigger step
            if (!array_key_exists($triggerParameter, $arguments)) {
                continue;
            }

            if (array_key_exists(self::FIELD_BASED_TRIGGER, $arguments)) {
                $max_relation_count = 100;
                if ($this->parameters->has('max_relation_count')) {
                    $max_relation_count = $this->parameters->get('max_relation_count', 100);
                }
                if (!$this->evaluateTriggerFields($arguments, $newDataNormalized, $oldDataNormalized, $max_relation_count)) {
                    continue;
                }
            }
            //Normalize workflow
            //TODO: check if this normalization has any fields different from old
            $normalizedBody = $this->workflowHelper->normalize_workflow_jsonld($workflow);
            //Update arguments on normalized workflow so they are not persisted
            unset($arguments[$triggerParameter]);
            array_push($applicableWorkflows, $normalizedBody);
        }

        if (sizeof($applicableWorkflows) > 0) {
            $headerVars = $event->getRequest()->headers->all();
            $requestBody = $this->workflowHelper->prepareWorkflowRequestBody($event->getRequest(), $triggerResource, $newDataNormalized, $oldDataNormalized);
            $isBulkTrigger = $event->getRequest()->attributes->get('fsr_subrequest_type') === 'bulk' ? true : false;
            $allWorkflows = [];
            foreach ($applicableWorkflows as $applicableWorkflow) {
                if (
                    $this->parameters->has('skip_recursive_playbook_execution')
                    && $this->parameters->get('skip_recursive_playbook_execution')
                    && array_key_exists('HTTP_X_CYOPS_PLAYBOOKIRI', $_SERVER)
                    && $_SERVER['HTTP_X_CYOPS_PLAYBOOKIRI'] == $applicableWorkflow['@id']
                ) {
                    $this->logger->warning("Skipping workflow to avoid infinite looping.");
                    continue;
                }
                $payload = $this->workflowHelper->prepareWorkflowTriggerPayload($triggerType, $requestBody, $applicableWorkflow, $headerVars);
                $data = $payload['payload'];
                $headers = $payload['headers'];
                if ($isBulkTrigger) {
                    array_push($allWorkflows, $data);
                } else {
                    $eventContext = ['workflowId' => $workflow->getUuid()];
                    $this->workflowHelper->invokeWorkflowEndpoint($data, $headers, $eventContext);
                }
            }
            if ($isBulkTrigger) {
                $event->getRequest()->attributes->set('fsr_workflow_triggers', $allWorkflows);
            }
        }
    }

    private function evaluateTriggerFields($arguments, $newData, $previousData, $max_relation_count)
    {
        return $this->filterUtility->evaluateObject($arguments[self::FIELD_BASED_TRIGGER], $newData, $previousData, $max_relation_count);
    }
}
