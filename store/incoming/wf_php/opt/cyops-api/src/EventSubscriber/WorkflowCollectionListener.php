<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\EventSubscriber;

use App\Entity\Workflow\Workflow;
use App\Entity\Workflow\WorkflowCollection;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Component\HttpKernel\Exception\BadRequestHttpException;

class WorkflowCollectionListener
{
    protected $entityManager;

    public function __construct(EntityManagerInterface $entityManager)
    {
        $this->entityManager = $entityManager;
    }

    public function preRemove(WorkflowCollection $workflowCollection)
    {
        $collectionUuid = $workflowCollection->getUuid();
        $entityRepo = $this->entityManager->getRepository(Workflow::class);
        $privateWorkflows = $entityRepo->findBy(['collection' => $collectionUuid, 'isPrivate' => true]);
        if (count($privateWorkflows)) {
            throw new BadRequestHttpException("Workflow Collection cannot be deleted, as it contains private playbooks, if you wish to delete make all playbooks of public");
        }
    }
}
