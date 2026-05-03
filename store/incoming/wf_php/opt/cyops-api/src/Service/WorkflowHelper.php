<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Service;

use Throwable;
use App\Constants\Triggers;
use Psr\Log\LoggerInterface;
use InvalidArgumentException;
use ApiPlatform\Api\IriConverterInterface;
use GuzzleHttp\Psr7\Request as GuzzleRequest;
use Symfony\Component\Serializer\SerializerInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpKernel\Exception\BadRequestHttpException;
use Symfony\Component\Security\Core\Authentication\Token\Storage\TokenStorageInterface;

class WorkflowHelper
{
    private $serializer;
    private $container;
    private $monolog;
    private $tokenStorage;
    private $iriConverter;

    const AUTH_METHOD_HEADER = 'X-CS-Authentication-Method';
    const NORMALIZER_METHOD = 'jsonld';

    public function __construct(
        SerializerInterface $serializer,
        ContainerInterface $container,
        IriConverterInterface $iriConverter,
        LoggerInterface $logger,
        TokenStorageInterface $tokenStorage
    ) {
        $this->tokenStorage = $tokenStorage;
        $this->serializer = $serializer;
        $this->container = $container;
        $this->iriConverter = $iriConverter;
        $this->monolog = $logger;
    }

    public function handleTrigger($triggerType, $newData, $workflow, $headerVars)
    {
        $payload = $this->prepareWorkflowTriggerPayload($triggerType, $newData, $workflow, $headerVars);
        $headers = $payload['headers'];
        $body = $payload['payload'];
        $eventContext = ['workflowId' => $workflow['@id']];
        return $this->invokeWorkflowEndpoint($body, $headers, $eventContext);
    }

    public function prepareWorkflowTriggerPayload($triggerType, $newData, $workflow, $headerVars)
    {
        //Normalize Arguments
        $defaultArguments = $newData;
        $authenticationMethods = [];

        if ($triggerType != Triggers::API_CALL) {
            $defaultArguments['request']['body'] = "";
        }
        if (array_key_exists('X-RUNBYUSER', $headerVars)) {
            $defaultArguments['request']['headers']['X-RUNBYUSER'] = $headerVars['X-RUNBYUSER'];
        }
        if (array_key_exists('X-TRIGGERTYPE', $headerVars)) {
            $defaultArguments['request']['headers']['X-TRIGGERTYPE'] = $headerVars['X-TRIGGERTYPE'];
        }

        foreach ($workflow['steps'] as &$normalizedStep) {
            if ($normalizedStep['@id'] == $workflow['triggerStep']) {
                $arguments = $normalizedStep['arguments'];
                if (isset($arguments['authentication_methods'])) {
                    $authenticationMethods = $arguments['authentication_methods'];
                    unset($arguments['authentication_methods']);
                }
                $normalizedStep['arguments'] = $defaultArguments + $normalizedStep['arguments'];
                break;
            }
        }

        $headers = ['Content-Type' => 'application/json'];
        if (!empty($authenticationMethods)) {
            $headers[self::AUTH_METHOD_HEADER] = implode(',', $authenticationMethods);
        }

        return ["payload" => $workflow, "headers" => $headers];
    }

    public function normalize_workflow_jsonld($workflow)
    {
        $context = [
            'relationships' => true,
            'ignore_authorization' => true,
            'ignore_field_authorization' => true,
            'ignore_relationship_authorization' => true,
            'ignore_depth' => true,
            'groups' => 'all',
            'resource_class' => $this->container->getParameter(Triggers::RESOURCES_MAP)[Triggers::WORKFLOW_RESOURCE]
        ];
        return $this->serializer->normalize(
            $workflow,
            self::NORMALIZER_METHOD,
            $context
        );
    }

    public function prepareWorkflowRequestBody($request, $resourceShortName, $data, $previous = null)
    {
        $result = [
            'request' => [
                'data' => $data,
                'method' => $request->getMethod(),
                'uri' => $request->getUri(),
                'baseUri' => $request->getUriForPath(""),
                'headers' => array_map(function ($item) {
                    return $item[0];
                }, $request->headers->all()),
                'body' => $request->getContent(),
                'query' => $request->query->all()
            ],
            'resource' => $resourceShortName
        ];

        if ($previous) {
            $result['previous'] = [
                'data' => $previous
            ];
        }

        try {
            $user = $this->tokenStorage->getToken()->getUser();
            $currentUserIri = $this->iriConverter->getIriFromResource($user);
            if (!is_null($currentUserIri)) {
                $result['currentUser'] = $currentUserIri;
            }
        } catch (Throwable $e) {
            $this->monolog->info(sprintf('No user token or matching user found for workflow trigger. Unauthenticated workflow triggers are not recommended '), ['requestUri' => $request->getUri()]);
        }
        return $result;
    }

    /**
     * @param $body
     * @param DataEvent $event
     * @param array $headers
     */
    public function invokeWorkflowEndpoint($body, $headers = [], $logContext = [])
    {
        $proxyClient = $this->container->get("app.proxy.client.workflow");
        $body = $this->serializer->encode(
            $body,
            'json'
        );
        $workflowRequestUri = $proxyClient->getTargetUri() . $this->container->getParameter('workflow_endpoint');
        if (array_key_exists('force_debug', $_GET) && $_GET['force_debug']) {
            $workflowRequestUri .= "?force_debug=true";
        }
        $request = new GuzzleRequest('POST', $workflowRequestUri, $headers, $body);
        $timeout = $this->container->getParameter('workflow.endpoint_timeout');

        $this->monolog->info(sprintf(
            'Waiting for up to %ds for a playbook response...',
            $timeout
        ), $logContext);

        try {
            $response = $proxyClient->send($request, [
                'timeout' => $timeout
            ]);
            return $response->getBody();
        } catch (InvalidArgumentException | \Exception $exception) {
            $errMsg = $exception->getMessage();
            $errCode = $exception->getCode();
            throw new BadRequestHttpException($errMsg);
        }
    }

    public function sealabRequest($uri, $method, $data = null)
    {
        $headers = [
            "Content-type" => "application/json",
        ];
        $body = $data ? $this->serializer->encode(
            $data,
            'json'
        ) : null;
        $workflowRequest = new GuzzleRequest($method, $uri, $headers, $body);
        $client = $this->container->get("app.proxy.client.rule");
        try {
            $response = $client->send($workflowRequest, ['verify' => false]);
            $statusCode = $response->getStatusCode();
            if ($statusCode < 400) {
                $jsonDecodeResponse = json_decode($response->getBody()->getContents(), true);
                return $jsonDecodeResponse != null && array_key_exists('hydra:member', $jsonDecodeResponse) ? $jsonDecodeResponse['hydra:member'] : $jsonDecodeResponse;
            } else {
                throw new \Exception($uri . '\n' . $response->getBody());
            }
        } catch (BadRequestHttpException | \Exception $exception) {
            $errVar = $exception->getResponse() ? $exception->getResponse()->getBody()->read(2048) : null;
            $errCode = $exception->getCode();
            throw new BadRequestHttpException(sprintf('%d: %s', $errCode, $errVar));
        }
    }
}
