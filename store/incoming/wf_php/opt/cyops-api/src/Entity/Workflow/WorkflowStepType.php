<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Entity\Workflow;

use ApiPlatform\Core\Annotation\ApiResource;
use App\Entity\Base\BaseEntity;
use App\Traits\Indexable;
use Doctrine\ORM\Mapping as ORM;
use Symfony\Component\Serializer\Annotation\Groups;
use ApiPlatform\Core\Annotation\ApiProperty;

/**
 *  @ApiResource(
 *     attributes={"validation_groups"={"fsr_primary", "fsr_all"}, "fsr_type"="workflow_step_types", "fsr_module"="workflows", "fsr_singular"="workflow_step_type"},
 *     normalizationContext={"ignore_depth"=true},
 *     denormalizationContext={"groups"={"fsr_all", "password"}, "fetch_data"=false, "fsr_type"="workflow_step_types"},
 *     collectionOperations={
 *          "get" = { "security_post_denormalize" = "is_granted('read.workflows', object)" }
 *     },
 *     itemOperations={
 *          "get" = { "security" = "is_granted('read.workflows', object)" }
 *     }
 * )
 * @ORM\Table(name="workflow_step_types")
 * @ORM\Entity()
 */
class WorkflowStepType extends BaseEntity
{

    use Indexable;
    
    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="string", length=255, nullable=false, unique=true)
     */
    private $name;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="string", length=255, nullable=false)
     */
    private $displayName;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="string", length=255, nullable=true)
     */
    private $widget;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\ManyToOne(targetEntity=StepTypeCollection::class, inversedBy="workflowStepTypes", cascade={"persist"})
     * @ORM\JoinColumn(name="collection_uuid", referencedColumnName="uuid", nullable=true)
     * @ApiProperty(readableLink=false)
     */
    private $collection;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="jsonb", nullable=true)
     */
    private $arguments = [];

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\ManyToOne(targetEntity=WorkflowStepType::class, inversedBy="parent", cascade={"persist"})
     * @ORM\JoinColumn(name="parent_uuid", referencedColumnName="uuid", nullable=true)
     */
    private $parent;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="string", length=150, nullable=true, options={"default":"fa fa-check-square-o"})
     */
    private $icon = 'fa fa-check-square-o';

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="string", length=10, nullable=true)
     */
    private $background;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="integer", nullable=true)
     */
    private $index;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="boolean", nullable=false, options={"default" = true})
     */
    private $visible = true;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="boolean", nullable=true, options={"default" = false})
     */
    private $deprecated = false;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="text", nullable=true)
     */
    private $description;

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

    public function getDisplayName(): ?string
    {
        return $this->displayName;
    }

    public function setDisplayName(?string $displayName): self
    {
        $this->displayName = $displayName;

        return $this;
    }

    public function getWidget(): ?string
    {
        return $this->widget;
    }

    public function setWidget(?string $widget): self
    {
        $this->widget = $widget;

        return $this;
    }

    public function getCollection(): ?StepTypeCollection
    {
        return $this->collection;
    }

    public function setCollection(?StepTypeCollection $collection): self
    {
        $this->collection = $collection;

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

    public function getParent(): ?self
    {
        return $this->parent;
    }

    public function setParent(?self $parent): self
    {
        $this->parent = $parent;

        return $this;
    }

    public function addParent(self $parent): self
    {
        if (!$this->parent->contains($parent)) {
            $this->parent[] = $parent;
            $parent->setParent($this);
        }

        return $this;
    }

    public function removeParent(self $parent): self
    {
        if ($this->parent->contains($parent)) {
            $this->parent->removeElement($parent);
            // set the owning side to null (unless already changed)
            if ($parent->getParent() === $this) {
                $parent->setParent(null);
            }
        }

        return $this;
    }

    public function getIcon(): ?string
    {
        return $this->icon;
    }

    public function setIcon(?string $icon): self
    {
        $this->icon = $icon;

        return $this;
    }

    public function getBackground(): ?string
    {
        return $this->background;
    }

    public function setBackground(?string $background): self
    {
        $this->background = $background;

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

    public function getDeprecated(): ?bool
    {
        return $this->deprecated;
    }

    public function setDeprecated(?bool $deprecated): self
    {
        $this->deprecated = $deprecated;

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
}
