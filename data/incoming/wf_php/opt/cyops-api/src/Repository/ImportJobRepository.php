<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Repository;


use App\Entity\Core\ImportJob;
use Doctrine\Persistence\ManagerRegistry;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;

/**
 * @method ImportJob|null find($id, $lockMode = null, $lockVersion = null)
 * @method ImportJob|null findOneBy(array $criteria, array $orderBy = null)
 * @method ImportJob[]    findAll()
 * @method ImportJob[]    findBy(array $criteria, array $orderBy = null, $limit = null, $offset = null)
 */
class ImportJobRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, ImportJob::class);
    }

}
