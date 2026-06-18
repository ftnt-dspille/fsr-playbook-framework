<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Repository;


use Doctrine\Persistence\ManagerRegistry;
use App\Entity\Workflow\WorkflowCollection;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;

/**
 * @method WorkflowCollection|null find($id, $lockMode = null, $lockVersion = null)
 * @method WorkflowCollection|null findOneBy(array $criteria, array $orderBy = null)
 * @method WorkflowCollection[]    findAll()
 * @method WorkflowCollection[]    findBy(array $criteria, array $orderBy = null, $limit = null, $offset = null)
 */
class WorkflowCollectionRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, WorkflowCollection::class);
    }

}
