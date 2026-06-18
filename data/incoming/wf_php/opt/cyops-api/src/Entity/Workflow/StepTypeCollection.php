<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Entity\Workflow;

use ApiPlatform\Core\Annotation\ApiResource;
use App\Entity\Base\BaseEntity;
use App\Repository\StepTypeCollectionRepository;
use App\Traits\Indexable;
use Doctrine\Common\Collections\ArrayCollection;
use Doctrine\Common\Collections\Collection;
use Doctrine\ORM\Mapping as ORM;
use Symfony\Component\Serializer\Annotation\Groups;

/**
 *  @ApiResource(
 *     attributes={"validation_groups"={"fsr_primary", "fsr_all"}, "fsr_type"="step_type_collections", "fsr_module"="workflows", "fsr_singular"="step_type_collection"},
 *     denormalizationContext={"groups"={"fsr_all", "password"}, "fetch_data"=false, "fsr_type"="step_type_collections"},
 *     normalizationContext={"ignore_depth"=true},
 *     collectionOperations={
 *          "get" = { "security_post_denormalize" = "is_granted('read.workflows', object)" }
 *     },
 *     itemOperations={
 *          "get" = { "security" = "is_granted('read.workflows', object)" }
 *     }
 * )
 * @ORM\Entity(repositoryClass=StepTypeCollectionRepository::class)
 * @ORM\Table(name="workflow_step_type_collection")
 */
class StepTypeCollection extends BaseEntity
{
    use Indexable;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="string", length=255, nullable=false)
     */
    private $name;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="integer", nullable=true)
     */
    private $index;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="boolean", nullable=false)
     */
    private $visible = true;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\OneToMany(targetEntity=WorkflowStepType::class, mappedBy="collection", cascade={"persist", "remove"})
     */
    private $stepTypes;

    public function __construct()
    {
        $this->stepTypes = new ArrayCollection();
    }

    public function getId(): ?int
    {
        return $this->id;
    }

    public function getName(): ?string
    {
        return $this->name;
    }

    public function setName(?string $name): self
    {
        $this->name = $name;

        return $this;
    }

    public function getIndex(): ?int
    {
        return $this->index;
    }

    public function setIndex(?int $index): self
    {
        $this->index = $index;

        return $this;
    }

    public function getVisible(): ?bool
    {
        return $this->visible;
    }

    public function setVisible(?bool $visible): self
    {
        $this->visible = $visible;

        return $this;
    }

    /**
     * @return Collection|WorkflowStepType[]
     */
    public function getStepTypes(): Collection
    {
        return $this->stepTypes;
    }

    public function addStepTypes(WorkflowStepType $workflowStepType): self
    {
        if (!$this->stepTypes->contains($workflowStepType)) {
            $this->stepTypes[] = $workflowStepType;
            $workflowStepType->setCollection($this);
        }

        return $this;
    }

    public function removeStepTypes(WorkflowStepType $workflowStepType): self
    {
        if ($this->stepTypes->contains($workflowStepType)) {
            $this->stepTypes->removeElement($workflowStepType);
            // set the owning side to null (unless already changed)
            if ($workflowStepType->getCollection() === $this) {
                $workflowStepType->setCollection(null);
            }
        }

        return $this;
    }
}
