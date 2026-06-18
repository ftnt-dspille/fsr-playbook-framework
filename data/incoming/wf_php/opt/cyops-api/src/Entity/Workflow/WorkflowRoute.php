<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Entity\Workflow;

use App\Entity\Base\BaseEntity;
use Doctrine\ORM\Mapping as ORM;
use App\Entity\Workflow\WorkflowStep;
use App\Entity\Workflow\WorkflowGroup;
use ApiPlatform\Core\Annotation\ApiProperty;
use ApiPlatform\Core\Annotation\ApiResource;
use Symfony\Component\Serializer\Annotation\Groups;

/**
 *  @ApiResource(
 *     attributes={"validation_groups"={"fsr_primary", "fsr_all"}, "fsr_type"="workflow_routes", "fsr_module"="workflows", "fsr_singular"="workflow_route"},
 *     normalizationContext={"ignore_depth"=true},
 *     denormalizationContext={"groups"={"fsr_all", "password"}, "fetch_data"=false, "fsr_type"="workflow_routes"},
 *     collectionOperations={
 *          "get" = { "security_post_denormalize" = "is_granted('read.workflows', object)" },
 *          "post" = { "security_post_denormalize" = "is_granted('create.workflows', object)" }
 *     },
 *     itemOperations={
 *          "get" = { "security" = "is_granted('read.workflows', object)" },
 *          "put" = { "security" = "is_granted('update.workflows', object)" },
 *          "delete" = { "security" = "is_granted('delete.workflows', object)" }
 *     }
 * )
 * @ORM\Table(name="workflow_routes")
 * @ORM\Entity()
 */
class WorkflowRoute extends BaseEntity
{

    /**
     * @Groups({"fsr_primary", "fsr_all", "name"})
     * @ORM\Column(type="string", length=255, nullable=true)
     */
    private $name;

    /**
     * @Groups({"fsr_primary", "fsr_all", "targetStep"})
     * @Doctrine\ORM\Mapping\ManyToOne(targetEntity="WorkflowStep")
     * @ORM\JoinColumn(name="targetstep_uuid", referencedColumnName="uuid", nullable=false, onDelete="CASCADE")
     * @ApiProperty(readableLink=false, writableLink=false)
     */
    protected $targetStep;

    /**
     * @Groups({"fsr_primary", "fsr_all", "sourceStep"})
     * @Doctrine\ORM\Mapping\ManyToOne(targetEntity="WorkflowStep")
     * @ORM\JoinColumn(name="sourcestep_uuid", referencedColumnName="uuid", nullable=false, onDelete="CASCADE")
     * @ApiProperty(readableLink=false, writableLink=false)
     */
    protected $sourceStep;

    /**
     * @Groups({"fsr_primary", "fsr_all", "label"})
     * @ORM\Column(type="string", length=255, nullable=true)
     */
    private $label;

    /**
     * @Groups({"fsr_primary", "fsr_all", "isExecuted"})
     * @ORM\Column(type="boolean", nullable=true)
     */
    private $isExecuted = false;

    /**
     * @var \Doctrine\Common\Collections\Collection
     *
     * @Doctrine\ORM\Mapping\ManyToMany(targetEntity="Workflow", mappedBy="routes", cascade={"persist"}, fetch="EXTRA_LAZY")
     * @Doctrine\ORM\Mapping\OrderBy({
     *     "modifyDate"="DESC"
     * })
     * @Groups({"workflows"})
     */
    protected $workflows;


    /**
     * @Groups({"fsr_primary", "fsr_all", "group"})
     * @Doctrine\ORM\Mapping\ManyToOne(targetEntity="WorkflowGroup", cascade={"persist"})
     * @ORM\JoinColumn(name="workflowgroup_uuid", referencedColumnName="uuid", nullable=true, onDelete="SET NULL")
     * @ApiProperty(readableLink=false, writableLink=false)
     */
    protected $group;

    public function getName(): ?string
    {
        return $this->name;
    }

    public function setName(?string $name): self
    {
        $this->name = $name;

        return $this;
    }

    public function getLabel(): ?string
    {
        return $this->label;
    }

    public function setLabel(?string $label): self
    {
        $this->label = $label;

        return $this;
    }

    public function getIsExecuted(): ?bool
    {
        return $this->isExecuted;
    }

    public function setIsExecuted(?bool $isExecuted): self
    {
        $this->isExecuted = $isExecuted;

        return $this;
    }

    /**
     * Set targetStep
     *
     * @param \App\Entity\Workflow\WorkflowStep $targetStep
     * @return WorkflowRoute
     */
    public function setTargetStep(WorkflowStep $targetStep)
    {
        $this->targetStep = $targetStep;

        return $this;
    }

    /** @return \App\Entity\Workflow\WorkflowStep */
    public function getTargetStep()
    {
        return $this->targetStep;
    }

    /**
     * Set sourceStep
     *
     * @param \App\Entity\Workflow\WorkflowStep $sourceStep
     * @return WorkflowRoute
     */
    public function setSourceStep(WorkflowStep $sourceStep)
    {
        $this->sourceStep = $sourceStep;

        return $this;
    }

    /** @return \App\Entity\Workflow\WorkflowStep */
    public function getSourceStep()
    {
        return $this->sourceStep;
    }

    /**
     * Get the value of workflows
     *
     * @return  \Doctrine\Common\Collections\Collection
     */
    public function getWorkflows()
    {
        return $this->workflows;
    }

    /**
     * Set the value of workflows
     *
     * @param  \Doctrine\Common\Collections\Collection  $workflows
     *
     * @return  self
     */
    public function setWorkflows(\Doctrine\Common\Collections\Collection $workflows)
    {
        $this->workflows = $workflows;

        return $this;
    }

    /**
     * Get the value of group
     */
    public function getGroup()
    {
        return $this->group;
    }

    /**
     * Set the value of group
     *
     * @return  self
     */
    public function setGroup($group)
    {
        $this->group = $group;

        return $this;
    }
}

