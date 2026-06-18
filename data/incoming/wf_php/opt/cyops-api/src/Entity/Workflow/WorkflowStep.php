<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Entity\Workflow;

use App\Entity\Base\BaseEntity;
use Doctrine\ORM\Mapping as ORM;
use App\Entity\Workflow\WorkflowGroup;
use App\Entity\Workflow\WorkflowStepType;
use ApiPlatform\Core\Annotation\ApiResource;
use ApiPlatform\Core\Annotation\ApiProperty;
use Symfony\Component\Serializer\Annotation\Groups;

/**
 *  @ApiResource(
 *     attributes={"validation_groups"={"fsr_primary", "fsr_all"}, "fsr_type"="workflow_steps", "fsr_module"="workflows", "fsr_singular"="workflow_step"},
 *     normalizationContext={"ignore_depth"=true},
 *     denormalizationContext={"groups"={"fsr_all", "password"}, "fetch_data"=false, "fsr_type"="workflow_steps"},
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
 * @ORM\Table(name="workflow_steps")
 * @ORM\Entity()
 */
class WorkflowStep extends BaseEntity
{

    /**
     * @Groups({"fsr_primary", "fsr_all", "name"})
     * @ORM\Column(type="string", length=255, nullable=false)
     */
    private $name;

    /**
     * @Groups({"fsr_primary", "fsr_all", "description"})
     * @ORM\Column(type="text", nullable=true)
     */
    private $description;

    /**
     * @Groups({"fsr_primary", "fsr_all", "arguments"})
     * @ORM\Column(type="jsonb", nullable=true)
     */
    private $arguments = [];

    /**
     * @Groups({"fsr_primary", "fsr_all", "status"})
     * @ORM\Column(type="string", length=255, nullable=true)
     */
    private $status;

    /**
     * @Groups({"fsr_primary", "fsr_all", "top"})
     * @ORM\Column(name="`top_position`", type="decimal", options={"default":0}, nullable=false)
     */
    private $top = 0;

    /**
     * @Groups({"fsr_primary", "fsr_all", "left"})
     * @ORM\Column(name="`left_position`", type="decimal", options={"default":0}, nullable=false)
     */
    private $left = 0;

    /**
     * @Groups({"fsr_primary", "fsr_all", "stepType"})
     * @ORM\ManyToOne(targetEntity="WorkflowStepType")
     * @ORM\JoinColumn(name="steptype_uuid", referencedColumnName="uuid", nullable=true)
     */
    protected $stepType;

    /**
     * @Groups({"fsr_primary", "fsr_all", "group"})
     * @Doctrine\ORM\Mapping\ManyToOne(targetEntity="WorkflowGroup", cascade={"persist"})
     * @ORM\JoinColumn(name="workflowgroup_uuid", referencedColumnName="uuid", nullable=true, onDelete="SET NULL")
     * @ApiProperty(readableLink=false, writableLink=false)
     */
    protected $group;

    /**
     * @var \Doctrine\Common\Collections\Collection
     *
     * @Doctrine\ORM\Mapping\ManyToMany(targetEntity="Workflow", mappedBy="steps", cascade={"persist"}, fetch="EXTRA_LAZY")
     * @Doctrine\ORM\Mapping\OrderBy({
     *     "modifyDate"="DESC"
     * })
     * @Groups({"workflows"})
     */
    protected $workflows;



    public function getName(): ?string
    {
        return $this->name;
    }

    public function setName(?string $name): self
    {
        $this->name = $name;

        return $this;
    }

    public function getDescription(): ?string
    {
        return $this->description;
    }

    public function setDescription(?string $description): self
    {
        $this->description = $description;

        return $this;
    }

    public function getArguments(): ?array
    {
        return $this->arguments;
    }

    public function setArguments(?array $arguments): self
    {
        $this->arguments = $arguments;

        return $this;
    }

    public function getStatus(): ?string
    {
        return $this->status;
    }

    public function setStatus(?string $status): self
    {
        $this->status = $status;

        return $this;
    }

    /**
     * Set left
     *
     * @param integer $left
     * @return WorkflowStep
     */
    public function setLeft($left)
    {
        $this->left = $left;

        return $this;
    }

    /**
     * Get left
     *
     * @return integer
     */
    public function getLeft()
    {
        return $this->left;
    }

    /**
     * Set top
     *
     * @param integer $top
     * @return WorkflowStep
     */
    public function setTop($top)
    {
        $this->top = $top;

        return $this;
    }

    /**
     * Get top
     *
     * @return integer
     */
    public function getTop()
    {
        return $this->top;
    }

    /**
     * Get the value of stepType
     */
    public function getStepType()
    {
        return $this->stepType;
    }

    /**
     * Set the value of stepType
     *
     * @return  self
     */
    public function setStepType($stepType)
    {
        $this->stepType = $stepType;

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
}

