<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Repository;

use App\Constants\AppConstants;
use App\Entity\Workflow\Workflow;
use Doctrine\Persistence\ManagerRegistry;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;

/**
 * @method Workflow|null find($id, $lockMode = null, $lockVersion = null)
 * @method Workflow|null findOneBy(array $criteria, array $orderBy = null)
 * @method Workflow[]    findAll()
 * @method Workflow[]    findBy(array $criteria, array $orderBy = null, $limit = null, $offset = null)
 */
class WorkflowRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, Workflow::class);
    }


    public function getWorkflowsForTriggerType($triggerType, $owners, $resource, $source=null, $triggerOnReplicate=false)
    {
        $workflowQueryBuilder = $this->createQueryBuilder('wf');

        if (!$owners) {
            /** @var Workflow[] $workflows */
            $queryBuilder = $workflowQueryBuilder
                ->join('wf.triggerStep', 'wfs')
                ->join('wfs.stepType', 'wfst')
                ->where($workflowQueryBuilder->expr()->eq('wfst.name', ':triggerType'))
                ->andWhere($workflowQueryBuilder->expr()->eq('wf.isActive', ':isActive'))
                ->setParameter('triggerType', $triggerType)
                ->setParameter('isActive', true);
        } else {
            /** @var Workflow[] $workflows */
            $queryBuilder = $workflowQueryBuilder
                ->join('wf.triggerStep', 'wfs')
                ->join('wfs.stepType', 'wfst')
                ->leftJoin('wf.owners', 'wfo')
                ->where($workflowQueryBuilder->expr()->eq('wfst.name', ':triggerType'))
                ->andWhere($workflowQueryBuilder->expr()->eq('wf.isActive', ':isActive'))
                ->andwhere(
                    $workflowQueryBuilder->expr()->orX(
                        $workflowQueryBuilder->expr()->eq('wf.isPrivate', ':isPrivate'),
                        $workflowQueryBuilder->expr()->in('wfo', ':owners')
                    )
                )
                ->setParameter('triggerType', $triggerType)
                ->setParameter('isActive', true)
                ->setParameter('isPrivate', false)
                ->setParameter('owners', $owners);
        }
        if ($resource) {
            $queryBuilder->andWhere("JSON_GET_TEXT(wfs.arguments, 'resource') = :resource");
            $queryBuilder->setParameter('resource', $resource);
        }

        // Keeping an argument of type origin
        // Possible value will include source or replicated
        if ($source == AppConstants::SOURCE_ORIGIN) {
            $queryBuilder->andWhere(
                $queryBuilder->expr()->orX(
                    $queryBuilder->expr()->eq("JSON_GET_TEXT(wfs.arguments, 'triggerOnSource')", ":triggerOnSource"),
                    $queryBuilder->expr()->eq("JSONB_EX(wfs.arguments, 'triggerOnSource')", 'false'),
                )
            );
            $queryBuilder->setParameter('triggerOnSource', 'true');
        } elseif ($source == AppConstants::SOURCE_REPLICATE) {
            if ($triggerOnReplicate) {
                $queryBuilder->andWhere(
                    $queryBuilder->expr()->orX(
                        $queryBuilder->expr()->eq("JSON_GET_TEXT(wfs.arguments, 'triggerOnReplicate')", ":triggerOnReplicate"),
                        $queryBuilder->expr()->eq("JSONB_EX(wfs.arguments, 'triggerOnReplicate')", 'false'),
                    )
                );
            } else {
                $queryBuilder->andWhere("JSON_GET_TEXT(wfs.arguments, 'triggerOnReplicate') = :triggerOnReplicate");
            }
            $queryBuilder->setParameter('triggerOnReplicate', 'true');
        }

        return $queryBuilder->getQuery()->execute();
    }
}

