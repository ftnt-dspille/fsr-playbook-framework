<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Entity\Workflow;

use App\Traits\Taggable;
use App\Entity\Base\BaseEntity;
use ApiPlatform\Core\Annotation\ApiProperty;
use Doctrine\ORM\Mapping as ORM;
use App\Entity\Workflow\WorkflowStep;
use App\Entity\Workflow\WorkflowRoute;
use ApiPlatform\Core\Annotation\ApiResource;
use Symfony\Component\Serializer\Annotation\Groups;

/**
 *  @ApiResource(
 *     attributes={"validation_groups"={"fsr_primary", "fsr_all"}, "fsr_type"="workflow_groups", "fsr_module"="workflows", "fsr_singular"="workflow_group"},
 *     denormalizationContext={"groups"={"fsr_all", "password"}, "fetch_data"=false, "fsr_type"="workflow_groups"},
 *     normalizationContext={"circular_reference_limit"=2},
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
 * @ORM\Table(name="workflow_groups")
 * @ORM\Entity()
 */
class WorkflowGroup extends BaseEntity
{
    use Taggable;

    /**
     * @Groups({"fsr_primary", "fsr_all", "name"})
     * @ORM\Column(type="string", length=140, nullable=false)
     */
    private $name;

    /**
     * @Groups({"fsr_primary", "fsr_all", "description"})
     * @ORM\Column(type="text", nullable=true)
     */
    private $description;

    /**
     * @Groups({"fsr_primary", "fsr_all", "type"})
     * @ORM\Column(type="string", length=255, nullable=false)
     */
    private $type;

    /**
     * @Groups({"fsr_primary", "fsr_all", "isCollapsed"})
     * @ORM\Column(type="boolean", nullable=true, options={"default" = false})
     */
    private $isCollapsed = false;

    /**
     * @Groups({"fsr_primary", "fsr_all", "hasTriggerStep"})
     * @ORM\Column(type="boolean", nullable=true, options={"default" = false})
     */
    private $hasTriggerStep = false;

    /**
     * @Groups({"fsr_primary", "fsr_all", "hideInLogs"})
     * @ORM\Column(type="boolean", nullable=true, options={"default" = false})
     */
    private $hideInLogs = false;

    /**
     * @var \Doctrine\Common\Collections\Collection
     *
     * @Doctrine\ORM\Mapping\OneToMany(targetEntity="App\Entity\Workflow\WorkflowStep", mappedBy="group", orphanRemoval=true, cascade={"persist", "remove"})
     * @ORM\OrderBy({"name" = "ASC"})
     * @Groups({"fsr_all", "workflowSteps"})
     */
    protected $workflowSteps;


    /**
     * @var \Doctrine\Common\Collections\Collection
     *
     * @Doctrine\ORM\Mapping\OneToMany(targetEntity="App\Entity\Workflow\WorkflowRoute", mappedBy="group", orphanRemoval=true, cascade={"persist", "remove"})
     * @ORM\OrderBy({"name" = "ASC"})
     * @Groups({"fsr_all", "workflowRoutes"})
     */
    protected $workflowRoutes;


    /**
     * @Groups({"fsr_primary", "fsr_all", "metadata"})
     * @ORM\Column(type="jsonb", nullable=true)
     */
    private $metadata = [];


    /**
     * @Groups({"fsr_primary", "fsr_all", "reusable"})
     * @ORM\Column(type="boolean", nullable=true, options={"default" = false})
     */
    private $reusable = false;

    /**
     * @Groups({"fsr_primary", "fsr_all", "top"})
     * @ORM\Column(name="top_position", type="decimal", options={"default":0}, nullable=false)
     */
    private $top = 0;

    /**
     * @Groups({"fsr_primary", "fsr_all", "left"})
     * @ORM\Column(name="left_position", type="decimal", options={"default":0}, nullable=false)
     */
    private $left = 0;

    /**
     * @Groups({"fsr_primary", "fsr_all", "height"})
     * @ORM\Column(name="height", type="decimal", options={"default":0}, nullable=false)
     */
    private $height = 0;

    /**
     * @Groups({"fsr_primary", "fsr_all", "width"})
     * @ORM\Column(name="width", type="decimal", options={"default":0}, nullable=false)
     */
    private $width = 0;

    /**
     * Constructor
     */
    public function __construct()
    {
        $this->workflowSteps = new \Doctrine\Common\Collections\ArrayCollection();
        $this->workflowRoutes = new \Doctrine\Common\Collections\ArrayCollection();
    }

    /**
     * Get the value of name
     */
    public function getName()
    {
        return $this->name;
    }

    /**
     * Set the value of name
     *
     * @return  self
     */
    public function setName($name)
    {
        $this->name = $name;

        return $this;
    }

    /**
     * Get WorkflowSteps
     *
     * @return \Doctrine\Common\Collections\Collection
     */
    public function getWorkflowSteps()
    {
        return $this->workflowSteps;
    }

    /**
     * Add WorkflowSteps
     *
     * @param \App\Entity\Workflow\WorkflowStep $workflowStep
     * @return WorkflowGroup
     */
    public function addWorkflowStep(WorkflowStep $workflowStep)
    {
        if (!$this->workflowSteps->contains($workflowStep)) {
            $this->workflowSteps[] = $workflowStep;
            $workflowStep->setGroup($this);
        }
        return $this;
    }

    /**
     * Remove WorkflowSteps
     *
     * @param \App\Entity\Workflow\WorkflowStep $WorkflowStep
     */
    public function removeWorkflowStep(WorkflowStep $workflowStep)
    {
        if ($this->workflowSteps->contains($workflowStep)) {
            $this->workflowSteps->removeElement($workflowStep);
            $workflowStep->setGroup(null);
        }
    }

    /**
     * Add workflowRoutes
     *
     * @param \App\Entity\Workflow\WorkflowRoute $workflowRoutes
     * @return WorkflowGroup
     */
    public function addWorkflowRoute(WorkflowRoute $workflowRoute)
    {
        if (!$this->workflowRoutes->contains($workflowRoute)) {
            $this->workflowRoutes[] = $workflowRoute;
            $workflowRoute->setGroup($this);
        }
        return $this;
    }

    /**
     * Remove workflowRoutes
     *
     * @param \App\Entity\Workflow\WorkflowRoute $workflowRoutes
     */
    public function removeWorkflowRoute(WorkflowRoute $workflowRoute)
    {
        if ($this->workflowRoutes->contains($workflowRoute)) {
            $this->workflowRoutes->removeElement($workflowRoute);
            $workflowRoute->setGroup(null);
        }
    }

    /**
     * Get workflowRoutes
     *
     * @return \Doctrine\Common\Collections\Collection
     */
    public function getWorkflowRoutes()
    {
        return $this->workflowRoutes;
    }

    public function getReusable(): ?bool
    {
        return $this->reusable;
    }

    public function setReusable(?bool $reusable): self
    {
        $this->reusable = $reusable;

        return $this;
    }

    /**
     * Get the value of top
     */
    public function getTop()
    {
        return $this->top;
    }

    /**
     * Set the value of top
     *
     * @return  self
     */
    public function setTop($top)
    {
        $this->top = $top;

        return $this;
    }

    /**
     * Get the value of left
     */
    public function getLeft()
    {
        return $this->left;
    }

    /**
     * Set the value of left
     *
     * @return  self
     */
    public function setLeft($left)
    {
        $this->left = $left;

        return $this;
    }

    /**
     * Get the value of height
     */
    public function getHeight()
    {
        return $this->height;
    }

    /**
     * Set the value of height
     *
     * @return  self
     */
    public function setHeight($height)
    {
        $this->height = $height;

        return $this;
    }

    /**
     * Get the value of width
     */
    public function getWidth()
    {
        return $this->width;
    }

    /**
     * Set the value of width
     *
     * @return  self
     */
    public function setWidth($width)
    {
        $this->width = $width;

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

    public function getType(): ?string
    {
        return $this->type;
    }

    public function setType(?string $type): self
    {
        $this->type = $type;

        return $this;
    }

    public function getIsCollapsed(): ?bool
    {
        return $this->isCollapsed;
    }

    public function setIsCollapsed(?bool $isCollapsed): self
    {
        $this->isCollapsed = $isCollapsed;

        return $this;
    }

    public function getHideInLogs(): ?bool
    {
        return $this->hideInLogs;
    }

    public function setHideInLogs(?bool $hideInLogs): self
    {
        $this->hideInLogs = $hideInLogs;

        return $this;
    }

    /**
     * Get the value of metadata
     */
    public function getMetadata()
    {
        return $this->metadata;
    }

    /**
     * Set the value of metadata
     *
     * @return  self
     */
    public function setMetadata($metadata)
    {
        $this->metadata = $metadata;

        return $this;
    }

    /**
     * Get the value of hasTriggerStep
     */
    public function getHasTriggerStep()
    {
        return $this->hasTriggerStep;
    }

    /**
     * Set the value of hasTriggerStep
     *
     * @return  self
     */
    public function setHasTriggerStep($hasTriggerStep)
    {
        $this->hasTriggerStep = $hasTriggerStep;

        return $this;
    }
}
