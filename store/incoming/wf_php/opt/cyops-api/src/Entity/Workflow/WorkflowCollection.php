<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Entity\Workflow;

use App\Traits\Indexable;
use App\Traits\Trackable;
use App\Traits\Importable;
use App\Traits\Taggable;
use App\Traits\SoftDeleteable;
use App\Entity\Base\BaseEntity;
use Doctrine\ORM\Mapping as ORM;
use Gedmo\Mapping\Annotation as Gedmo;
use ApiPlatform\Core\Annotation\ApiResource;
use App\Repository\WorkflowCollectionRepository;
use Doctrine\Common\Collections\ArrayCollection;
use Symfony\Component\Serializer\Annotation\Groups;

/**
 *  @ApiResource(
 *     attributes={"validation_groups"={"fsr_primary", "fsr_all"}, "fsr_type"="workflow_collections", "fsr_module"="workflows", "fsr_singular"="workflow_collection"},
 *     denormalizationContext={"groups"={"fsr_all", "password"}, "fetch_data"=false, "fsr_type"="workflow_collections"},
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
 * @Gedmo\SoftDeleteable(fieldName="deletedAt")
 * @ORM\Entity(repositoryClass=WorkflowCollectionRepository::class)
 * @ORM\EntityListeners({"App\EventSubscriber\WorkflowCollectionListener"})
 * @Doctrine\ORM\Mapping\Table(name="workflow_collections", indexes={@Doctrine\ORM\Mapping\Index(name="workflow_collections_deletedat_idx", columns={"deletedat"}, options={"where": "(deletedat IS NULL)"})})
 */
class WorkflowCollection extends BaseEntity
{

    use Indexable;
    use Trackable;
    use SoftDeleteable;
    use Importable;
    use Taggable;
    /**
     * @Groups({"fsr_primary", "fsr_all", "name"})
     * @ORM\Column(type="string", length=255, nullable=false, unique=true)
     */
    private $name;

    /**
     * @Groups({"fsr_primary", "fsr_all", "description"})
     * @ORM\Column(type="text", nullable=true)
     */
    private $description;

    /**
     * @Groups({"fsr_primary", "fsr_all", "visible"})
     * @ORM\Column(type="boolean", nullable=false)
     */
    private $visible = true;

    /**
     * @Groups({"fsr_all", "workflows"})
     * @ORM\OneToMany(targetEntity=Workflow::class, mappedBy="collection", orphanRemoval=true, cascade={"persist", "remove"})
     */
    private $workflows;

    /**
     * @var string
     * @Groups({"fsr_primary", "fsr_all", "image"})
     * @Doctrine\ORM\Mapping\Column(name="`image`", type="string", nullable=true, unique=false)
     *
     */
    protected $image;

    public function __construct()
    {
        $this->workflows = new ArrayCollection();
    }

    public function getId(): ?int
    {
        return $this->id;
    }

    public function getName(): ?string
    {
        return $this->name;
    }

    public function setName(string $name): self
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

    public function getVisible(): ?bool
    {
        return $this->visible;
    }

    public function setVisible(?bool $visible): self
    {
        $this->visible = $visible;

        return $this;
    }

    public function getWorkflows()
    {
        if (array_key_exists('$workflowCountOnly', $_GET)) {
            return [];
        }
        return $this->workflows;
    }

    /**
     * @Groups({"workflowCount"})
     */
    public function getWorkflowCount()
    {
        return $this->workflows->count();
    }

    public function addWorkflow(Workflow $workflow): self
    {
        if (!$this->workflows->contains($workflow)) {
            $this->workflows[] = $workflow;
            $workflow->setCollection($this);
        }

        return $this;
    }

    public function removeWorkflow(Workflow $workflow): self
    {
        if ($this->workflows->contains($workflow)) {
            $this->workflows->removeElement($workflow);
            // set the owning side to null (unless already changed)
            if ($workflow->getCollection() === $this) {
                $workflow->setCollection(null);
            }
        }

        return $this;
    }

    /**
     * Get the value of image
     *
     */
    public function getImage()
    {
        return $this->image;
    }

    /**
     * Set the value of image
     *
     * @return  self
     */
    public function setImage($image)
    {
        $this->image = $image;

        return $this;
    }
}
