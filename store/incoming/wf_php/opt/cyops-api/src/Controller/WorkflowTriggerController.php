<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Controller;

use App\Constants\Triggers;
use App\Entity\Actors\Actor;
use Psr\Log\LoggerInterface;
use App\Utility\StatsUtility;
use InvalidArgumentException;
use App\Constants\AppConstants;
use App\Service\MetadataHelper;
use App\Service\UtilityService;
use App\Service\WorkflowHelper;
use App\Security\Voter\FsrVoter;
use App\Entity\Workflow\Workflow;
use Doctrine\ORM\EntityManagerInterface;
use GuzzleHttp\Psr7\Request as GuzzleRequest;
use Symfony\Component\HttpFoundation\Request;
use GuzzleHttp\Exception\BadResponseException;
use Symfony\Component\HttpFoundation\Response;
use App\Providers\PermissionsDictionaryBuilder;
use Symfony\Component\HttpFoundation\JsonResponse;
use ApiPlatform\Api\ResourceClassResolverInterface;
use Symfony\Contracts\Cache\TagAwareCacheInterface;
use App\EventSubscriber\MqMessagebroadcastSubscriber;
use Symfony\Component\Serializer\SerializerInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;
use Symfony\Component\HttpKernel\Exception\BadRequestHttpException;
use Symfony\Component\Security\Core\Exception\AccessDeniedException;
use Symfony\Component\Security\Core\Authentication\Token\Storage\TokenStorageInterface;

class WorkflowTriggerController extends BaseController
{
    public const RESOURCE_PARAM = 'resource';
    public const ROUTE_PARAM = 'route';
    public const DELTA_DATA = 'data';
    public const HTTP_METHOD = 'operation';
    public const REMOTE_ADDR = 'source';
    public const WEB_SOCKET_SESSION_ID = 'websocketId';
    public const COMPONENT = 'component';
    public const UUID = 'entityUuid';
    public const USER_UUID = 'userId';
    public const USER = 'user';
    public const TRANSACTION_DATE = 'transactionDate';
    public const PLAYBOOK_IRI = 'playbookIri';
    public const PLAYBOOK_NAME = 'playbookName';
    public const PEOPLE_IRI = '/api/3/people/';

    public function __construct(
        private FsrVoter $fsrVoter,
        protected SerializerInterface $serializer,
        private EntityManagerInterface $entityManager,
        protected WorkflowHelper $workflowHelper,
        ResourceClassResolverInterface $resourceClassResolver,
        ContainerInterface $containers,
        TagAwareCacheInterface $cache,
        MetadataHelper $metadataHelper,
        private UtilityService $utilityService,
        protected TokenStorageInterface $tokenStorage,
        protected LoggerInterface $logger,
        protected StatsUtility $statsUtility
    ) {
        parent::__construct($resourceClassResolver, $containers, $cache, $metadataHelper, $serializer, $logger);
    }

    public function postManualAction(Request $request, $workflowid)
    {
        $headerObj = [];
        if (!$this->fsrVoter->isGranted(PermissionsDictionaryBuilder::PERM_CRUD_EXECUTE . '.' . Triggers::WORKFLOW_RESOURCE)) {
            throw new AccessDeniedException();
        }
        $auditArray = [];
        $body = json_decode($request->getContent(), true);
        [$data, $resource] = $this->extractDataFromRequest($body);
        if (array_key_exists("__uuid", $data)) {
            $workflowId = $data['__uuid'];
        } else {
            throw new NotFoundHttpException('Workflow UUID Not Found In Request');
        }
        $workflowObj = $this->fetch_workflow_data($workflowId);
        $trigger = Triggers::ACTION;
        $headerObj['X-TRIGGERTYPE'] = Triggers::ACTION;
        //Check authorization on action trigger

        if (isset($body['singleRecordExecution']) && $body['singleRecordExecution'] === true) {
            $taskIds = [];

            $clonedRecordData = $data;
            unset($clonedRecordData['records']);
            foreach ($data['records'] as $record) {
                $headerObj['X-RUNBYUSER'] = self::PEOPLE_IRI . $this->getUser()->getUuid();
                $clonedRecordData['records'] = [$record];
                array_push(
                    $auditArray,
                    $this->prepareChangeData(
                        $clonedRecordData['records'],
                        (object)null,
                        'Trigger',
                        $workflowObj['@id'],
                        $workflowObj['name']
                    )
                );
                $requestBody = $this->workflowHelper->prepareWorkflowRequestBody($request, $workflowid, $clonedRecordData, null);
                $workflowResponse = $this->workflowHelper->handleTrigger($trigger, $requestBody, $workflowObj, $headerObj);
                array_push($taskIds, json_decode($workflowResponse)->task_id);
            }
            if (!empty($taskIds) && !in_array(AppConstants::IGNORE_TAG_FOR_SUGGESTION, $workflowObj['recordTags'])) {
                $this->statsUtility->saveStats(
                    $resource,
                    $body['records'],
                    'Workflow',
                    $workflowId,
                    $workflowObj['name'],
                    $taskIds
                );
            }
            $this->containers->get('old_sound_rabbit_mq.cyops_crud_auditing_producer')->setContentType('application/json');
            $this->containers->get('old_sound_rabbit_mq.cyops_crud_auditing_producer')->publish(json_encode($auditArray), MqMessagebroadcastSubscriber::DEFAULT_KEY);
            return new JsonResponse([
                'task_ids' => $taskIds
            ]);
        } else {
            $headerObj['X-RUNBYUSER'] = self::PEOPLE_IRI . $this->getUser()->getUuid();
            $requestBody = $this->workflowHelper->prepareWorkflowRequestBody($request, $workflowid, $data, null);
            $workflowResponse = $this->workflowHelper->handleTrigger($trigger, $requestBody, $workflowObj, $headerObj);
            $responseObj = json_decode($workflowResponse, true);
            if (!empty($responseObj['task_id']) && !in_array(AppConstants::IGNORE_TAG_FOR_SUGGESTION, $workflowObj['recordTags'])) {
                $this->statsUtility->saveStats(
                    $resource,
                    $body['records'],
                    'Workflow',
                    $workflowId,
                    $workflowObj['name'],
                    [$responseObj['task_id']]
                );
            }
            array_push(
                $auditArray,
                $this->prepareChangeData(
                    $data['records'],
                    (object)null,
                    'Trigger',
                    $workflowObj['@id'],
                    $workflowObj['name']
                )
            );
            $this->containers->get('old_sound_rabbit_mq.cyops_crud_auditing_producer')->setContentType('application/json');
            $this->containers->get('old_sound_rabbit_mq.cyops_crud_auditing_producer')->publish(json_encode($auditArray), MqMessagebroadcastSubscriber::DEFAULT_KEY);
            return new JsonResponse($responseObj);
        }
    }

    public function noTriggerExecuteAction(Request $request, $workflowId)
    {
        $errMsg = "";
        if (!$this->fsrVoter->isGranted(PermissionsDictionaryBuilder::PERM_CRUD_EXECUTE . '.' . Triggers::WORKFLOW_RESOURCE)) {
            throw new AccessDeniedException();
        }
        $body = json_decode($request->getContent(), true);
        $body['request']['method'] = $request->getMethod();
        $body['request']['uri'] = $request->getUri();
        $body['request']['baseUri'] = 'https://' . $request->getHost();
        $body['request']['currentUser'] = self::PEOPLE_IRI . $this->getUser()->getUuid();
        $body['currentUser'] = self::PEOPLE_IRI . $this->getUser()->getUuid();
        $body['request']['headers'] = $this->getHeaders($request->headers->all());

        $normalizedData = $this->fetch_workflow_data($workflowId);
        $triggerStepIri = $normalizedData['triggerStep'] ?? null;

        foreach ($normalizedData['steps'] as &$normalizedStep) {
            if ($normalizedStep['@id'] === $triggerStepIri) {
                $normalizedStep['arguments'] = array_merge($normalizedStep['arguments'], $body);
                if (isset($normalizedStep['arguments']['inputVariables']) && (is_countable($normalizedStep['arguments']['inputVariables']) ? count($normalizedStep['arguments']['inputVariables']) : 0) > 0) {
                    foreach ($normalizedStep['arguments']['inputVariables'] as $userInput) {
                        $normalizedStep['arguments']['request']['data'][$userInput['name']] = $normalizedStep['arguments'][$userInput['name']];
                    }
                }
                break;
            }
        }

        if (isset($body['_eval_input_params_from_env'])) {
            $normalizedData['_eval_input_params_from_env'] = $body['_eval_input_params_from_env'];
        }

        if (isset($body['parent_wf'])) {
            $normalizedData['parent_wf'] = $body['parent_wf'];
        }

        if (isset($body['step_id'])) {
            $normalizedData['step_id'] = $body['step_id'];
        }

        if (isset($body['env'])) {
            $normalizedData['env'] = $body['env'];
            $normalizedData['debug'] = array_key_exists('debug', $body['env']) ? $body['env']['debug']: false;
        }

        if (isset($body['priority'])) {
            $normalizedData['priority'] = $body['priority'];
        }

        // For tags added temporarily during execution of playbook. Used for tag based filter on executed playbooks
        if (isset($body['runtime_tags'])) {
            $normalizedData['runtime_tags'] = $body['runtime_tags'];
        }

        if (isset($body['force_debug'])) {
            $normalizedData['force_debug'] = $body['force_debug'];
        }

        $token = $this->tokenStorage->getToken();
        $headers = ["Content-type" => "application/json"];
        $headers['Authorization'] = "Bearer " . $token->getCredentials();
        $headers['X-RUNBYUSER'] = self::PEOPLE_IRI . $this->getUser()->getUuid();
        $headers['X-TRIGGERTYPE'] = Triggers::NOTRIGGER;

        $body = $this->serializer->encode(
            $normalizedData,
            'json'
        );
        $proxyClient = $this->containers->get("app.proxy.client.workflow");
        $workflowRequestUri = $proxyClient->getTargetUri() . $this->getParameter('workflow_endpoint');
        $workflowRequest = new GuzzleRequest('post', $workflowRequestUri, $headers, $body);
        try {
            $response = $proxyClient->send($workflowRequest);
            $statusCode = $response->getStatusCode();
            if ($statusCode >= 400) {
                return new JsonResponse("Failed to get response from Workflow log", $statusCode);
            } else {
                $jsonDecodeResponse = json_decode($response->getBody()->getContents(), true);
                return new JsonResponse($jsonDecodeResponse, $statusCode);
            }
        } catch (BadRequestHttpException $e) {
            $errMsg = $e->getMessage();
            $errCode = $e->getCode();
            $this->logger->error($errMsg);
            return new JsonResponse($errMsg, $errCode);
        } catch (\Exception $exception) {
            // TODO: match response when workflow api returns non OK response
            // 502 bad gateway is only handled currently
            $errMsg = $exception->getMessage();
            $errCode = $exception->getCode();
            return new JsonResponse(['message' => $errMsg], $errCode);
        }
    }

    public function apiAction(Request $request, $apiEndpoint)
    {
        $body = $request->getContent();
        $data = json_decode($body, true);
        if ($this->getUser() != null) {
            if (!$this->fsrVoter->isGranted(PermissionsDictionaryBuilder::PERM_CRUD_EXECUTE . '.' . Triggers::WORKFLOW_RESOURCE)) {
                throw new AccessDeniedException();
            }
            if (method_exists($this->getUser(), "getfirstname")) {
                $headerObj['X-RUNBYUSER'] = self::PEOPLE_IRI . $this->getUser()->getUuid();
            } else {
                $headerObj['X-RUNBYUSER'] = '/api/3/appliance/' . $this->getUser()->getUuid();
            }
        } elseif (isset($_SERVER['PHP_AUTH_USER'])) {
            $loginId = $_SERVER['PHP_AUTH_USER'];
            $userId = $this->getUserId($loginId);
            if ($userId != null) {
                $userUuid = $this->getuuid($userId);
                $headerObj['X-RUNBYUSER'] = self::PEOPLE_IRI . $userUuid;
            } else {
                $headerObj['X-RUNBYUSER'] = "";
            }
        } else {
            $headerObj['X-RUNBYUSER'] = "";
        }
        $headerObj['X-TRIGGERTYPE'] = Triggers::API_CALL;
        $workflowRepository = $this->entityManager->getRepository(Workflow::class);
        $workflows = $workflowRepository->getWorkflowsForTriggerType(Triggers::API_CALL, null, null);
        if (empty($workflows)) {
            return new JsonResponse(array('message' => 'No active workflow matching the given route.'), Response::HTTP_NOT_FOUND);
        }
        $taskIds = [];
        foreach ($workflows as $workflow) {
            $triggerStep = $workflow->getTriggerStep();
            $arguments = $triggerStep->getArguments();

            # TODO: needs to be handled for API trigger
            $triggerParameter = self::ROUTE_PARAM;

            //Validate trigger step
            if (!array_key_exists($triggerParameter, $arguments)) {
                continue;
            }
            if ($arguments[$triggerParameter] != $apiEndpoint) {
                continue;
            }

            //Normalize workflow
            $normalizeWorkflow = $this->workflowHelper->normalize_workflow_jsonld($workflow);
            //Update arguments on normalized workflow so they are not persisted
            unset($arguments[$triggerParameter]);
            $requestBody = $this->workflowHelper->prepareWorkflowRequestBody($request, $apiEndpoint, is_null($data) ? $body : $data, null);
            $workflow_response = $this->workflowHelper->handleTrigger(Triggers::API_CALL, $requestBody, $normalizeWorkflow, $headerObj);
            $taskIds[] = json_decode($workflow_response, true)['task_id'];
        }
        // Added the below if just to maintain backward compatability of response.
        if (empty($taskIds)) {
            return new JsonResponse(array('message' => 'No active workflow matching the given route.'), Response::HTTP_NOT_FOUND);
        } else if (count($taskIds) == 1) {
            return new JsonResponse(["task_id" => $taskIds[0]]);
        }
        return new JsonResponse(["task_id" => $taskIds]);
    }

    protected function extractDataFromRequest($data)
    {
        if (array_key_exists("__resource", $data)) {
            $resourceShortName = $data['__resource'];
        } else {
            throw $this->createNotFoundException('Resource Not Found In Request');
        }
        $resourceClass = $this->getResourceFromClassName($resourceShortName);

        if (!($this->fsrVoter->isGranted(PermissionsDictionaryBuilder::PERM_CRUD_READ . '.' . $resourceShortName))) {
            throw new AccessDeniedException();
        }
        $resourceContext = ['resource_class' => $resourceClass];

        $entityRepository = $this->entityManager->getRepository($resourceClass);
        $denormalizedObjects = $this->utilityService->getItemWithWhere($entityRepository, ['uuid' => $data['records']]);
        foreach ($denormalizedObjects as $index => $object) {
            $normalizedData = $this->serializer->normalize(
                $object,
                self::NORMALIZER_METHOD,
                $resourceContext
            );
            $data['records'][$index] = $normalizedData;
        }
        return [$data, $resourceShortName];
    }

    private function fetch_workflow_data($workflowId)
    {
        $workflowRepository = $this->entityManager->getRepository(Workflow::class);
        $workflowObject = $workflowRepository->find($workflowId);
        if (!$workflowObject) {
            throw $this->createNotFoundException(
                'No workflow found for id ' . $workflowId
            );
        }
        return $this->workflowHelper->normalize_workflow_jsonld($workflowObject);
    }

    protected function prepareChangeData($updatedObject, $previousObject, $method, $playbook_iri, $playbook_name, $changeData = [])
    {
        $deltaData = [];
        $deltaData['oldData'] = $previousObject;
        $deltaData['newData'] = $updatedObject;
        $deltaData['changeData'] = $changeData;
        $userName = $this->extractUserName();
        return [
            self::DELTA_DATA => $deltaData,
            self::HTTP_METHOD => $method,
            self::REMOTE_ADDR => $_SERVER['REMOTE_ADDR'],
            self::COMPONENT => 'crudhub',
            self::USER_UUID => $this->getUser()->getUuid(),
            self::TRANSACTION_DATE => (int)($_SERVER['REQUEST_TIME_FLOAT'] * 1000),
            self::USER => $userName,
            self::PLAYBOOK_IRI => $playbook_iri,
            self::PLAYBOOK_NAME => $playbook_name
        ];
    }

    private function extractUserName()
    {
        if (method_exists($this->getUser(), "getfirstname")) {
            if (method_exists($this->getUser(), "getlastname")) {
                $userName = $this->getUser()->getfirstname() . ' ' . $this->getUser()->getlastname();
            } else {
                $userName = $this->getUser()->getfirstname();
            }
        } else {
            $userName = $this->getUser()->getname();
        }
        return $userName;
    }

    private function getHeaders($headers)
    {
        $headerList = [];
        foreach ($headers as $header => $value) {
            $headerList[$header] = $value[0];
        }
        return $headerList;
    }

    private function getUserId($loginId)
    {
        $client = $this->findHandlerForRoute('auth');
        $body = ["json" => ["loginid" => $loginId]];
        $userRequestUri = sprintf("%s/%s", $client->getTargetUri(), 'users');
        $response = null;
        try {
            $response = $client->request('POST', $userRequestUri, $body);
            $respBody = json_decode($response->getBody()->getContents(), true);
            return $respBody['uuid'];
        } catch (BadResponseException $exception) {
            return null;
        } catch (\Exception $e) {
            $this->logger->error('Failure: ' . $e->getMessage());
            return null;
        }
    }

    private function getuuid($userId)
    {
        $actorRepo = $this->entityManager->getRepository(Actor::class);
        try {
            $actor = $actorRepo->findOneBy(['userId' => $userId]);
            return $actor->getUuid();
        } catch (InvalidArgumentException | \Exception $e) {
            $this->logger->error($e->getMessage());
            return '';
        }
    }

    private function findHandlerForRoute($routeIdentifier)
    {
        $handler = $this->findHandlerMapForRoute($routeIdentifier);

        return $this->containers->get($handler[$routeIdentifier]['handlerName']);
    }

    private function findHandlerMapForRoute($routeIdentifier)
    {
        $handlerMap = $this->getParameter('app.proxy.handler.map');
        //$this->getParameter('app_proxy')['handlers'] this is workign

        if (!array_key_exists($routeIdentifier, $handlerMap)) {
            throw new NotFoundHttpException();
        }
        return $handlerMap;
    }
}
