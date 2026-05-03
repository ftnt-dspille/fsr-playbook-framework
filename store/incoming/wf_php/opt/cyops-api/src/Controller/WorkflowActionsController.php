<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Controller;

use App\Entity\Workflow\Workflow;
use App\Security\Voter\FsrVoter;
use Symfony\Component\Security\Core\Exception\AccessDeniedException;
use App\Query\ExpressionBuilder;
use Symfony\Component\HttpFoundation\Request;
use App\Providers\QueryProvider;
use App\Constants\Triggers;
use ApiPlatform\Core\DataProvider\CollectionDataProviderInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\Serializer\SerializerInterface;
use Symfony\Component\HttpFoundation\JsonResponse;
use App\Providers\PermissionsDictionaryBuilder;

class WorkflowActionsController extends AbstractController
{
    /** @var  FsrVoter */
    private $fsrVoter;

    /** @var  QueryProvider */
    private $queryProvider;

    /** @var CollectionDataProviderInterface */
    private $collectionDataProvider;

    /** SerializerInterface */
    private $serializer;

    public function __construct(FsrVoter $fsrVoter, QueryProvider $queryProvider, CollectionDataProviderInterface $collectionDataProvider, SerializerInterface $serializer)
    {
        $this->fsrVoter = $fsrVoter;
        $this->queryProvider = $queryProvider;
        $this->collectionDataProvider = $collectionDataProvider;
        $this->serializer = $serializer;
    }

    public function getManualActions(Request $request)
    {
        if (!($this->fsrVoter->isGranted(PermissionsDictionaryBuilder::PERM_CRUD_EXECUTE . '.' . Triggers::WORKFLOW_RESOURCE) || $this->fsrVoter->isGranted(PermissionsDictionaryBuilder::PERM_CRUD_READ . '.' . Triggers::WORKFLOW_RESOURCE))) {
            throw new AccessDeniedException();
        }
        $type = $request->query->get('type');
        $queryLimit = $request->get('$limit', 250);
        $queryPage = $request->get('$page', 1);
        $query = $this->buildActionQuery($type);
        $this->queryProvider->setInitialQuery($query->toArray());
        $workflowResource = Workflow::class;
        $attributes = [];
        $attributes['filters'] = ['$limit' => $queryLimit, '$page' => $queryPage];
        $attributes['resource_class'] = $workflowResource;
        $attributes['collection_operation_name'] = "get";
        $data = $this->collectionDataProvider->getCollection($workflowResource, $request, $attributes);

        //TODO: check if this normalization has any fields different from old
        $normalizedActions = $this->serializer->normalize(
            $data,
            'jsonld',
            array(
                'ignore_authorization' => true,
                'ignore_field_authorization' => true,
                'ignore_relationship_authorization' => true,
                'relationships' => true,
                'resource_class' => $workflowResource,
            )
        );
        return new JsonResponse($normalizedActions);
    }

    /**
     * @param Request $request
     * @return Query
     */
    protected function buildActionQuery($type)
    {
        $query = ExpressionBuilder::logicAnd()
            ->addFilter(ExpressionBuilder::field('isActive')->equals(true))
            ->addFilter(ExpressionBuilder::field('triggerStep.stepType.name')->equals('cybersponse.action'));

        $sort['field'] = "name";
        $sort['direction'] = "ASC";
        $query->addSort($sort);
        if ($type) {
            $query->addFilter(ExpressionBuilder::field('triggerStep.arguments.resources')->exists($type));
            return $query;
        }
        return $query;
    }
}
