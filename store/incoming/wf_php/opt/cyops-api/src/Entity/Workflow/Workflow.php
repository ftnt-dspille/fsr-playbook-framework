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
use App\Entity\Core\Picklist;
use App\Traits\SoftDeleteable;
use App\Entity\Base\BaseEntity;
use Doctrine\ORM\Mapping as ORM;
use App\Traits\ConditionalOwnable;
use App\Repository\WorkflowRepository;
use Gedmo\Mapping\Annotation as Gedmo;
use Doctrine\ORM\Mapping\UniqueConstraint;
use Doctrine\Common\Collections\Collection;
use ApiPlatform\Core\Annotation\ApiProperty;
use ApiPlatform\Core\Annotation\ApiResource;
use Doctrine\Common\Collections\ArrayCollection;
use Symfony\Component\Serializer\Annotation\Groups;

/**
 *  @ApiResource(
 *     attributes={"validation_groups"={"fsr_primary", "fsr_all"}, "fsr_type"="workflows", "fsr_module"="workflows", "fsr_singular"="Workflow"},
 *     denormalizationContext={"groups"={"fsr_all", "password"}, "fetch_data"=false, "fsr_type"="workflows"},
 *     normalizationContext={"ignore_depth"=true},
 *     collectionOperations={
 *          "get" = { "security_post_denormalize" = "is_granted('read.workflows', object)" },
 *          "post" = { "security_post_denormalize" = "is_granted('create.workflows', object)" }
 *     },
 *     itemOperations={
 *          "get" = { "security" = "is_granted('read.workflows', object)" },
 *          "put" = { "security" = "is_granted('update.workflows', object)" },
 *          "delete" = { "security" = "is_granted('delete.workflows', object)" }
 *     },
 *     subresourceOperations={
 *          "owners_get_subresource" = {"path"="workflows/{uuid}/owners"},
 *     }
 * )
 * @ORM\Entity(repositoryClass=WorkflowRepository::class)
 * @Gedmo\SoftDeleteable(fieldName="deletedAt")
 * @ORM\Table(name="workflows", uniqueConstraints={@UniqueConstraint(name="name_unique", columns={"name", "collection"})}, indexes={@Doctrine\ORM\Mapping\Index(name="workflows_modifydate_idx", columns={"modifydate"}), @Doctrine\ORM\Mapping\Index(name="workflows_createdate_idx", columns={"createdate"}), @Doctrine\ORM\Mapping\Index(name="workflows_id_idx", columns={"id"}), @Doctrine\ORM\Mapping\Index(name="workflows_deletedat_idx", columns={"deletedat"}, options={"where": "(deletedat IS NULL)"})})
 */
class Workflow extends BaseEntity
{

    use Indexable;
    use Trackable;
    use ConditionalOwnable;
    use SoftDeleteable;
    use Importable;
    use Taggable;

    /**
     * @Groups({"fsr_primary", "fsr_all", "triggerLimit"})
     * @ORM\Column(type="integer", nullable=true)
     */
    private $triggerLimit;

    /**
     * @Groups({"fsr_primary", "fsr_all", "name"})
     * @ORM\Column(type="string", length=255, nullable=false)
     */
    private $name;

    /**
     * @Groups({"fsr_primary", "fsr_all", "aliasName"})
     * @ORM\Column(type="string", length=255, nullable=true)
     */
    private $aliasName;

    /**
     * @Groups({"fsr_primary", "fsr_all", "tag"})
     * @ORM\Column(type="string", length=255, nullable=true)
     */
    private $tag;

    /**
     * @Groups({"fsr_primary", "fsr_all", "description"})
     * @ORM\Column(type="text", nullable=true)
     */
    private $description;

    /**
     * @Groups({"fsr_primary", "fsr_all", "isActive"})
     * @ORM\Column(type="boolean", nullable=true, options={"default" = false})
     */
    private $isActive = false;

    /**
     * @Groups({"fsr_primary", "fsr_all", "debug"})
     * @ORM\Column(type="boolean", nullable=true, options={"default" = false})
     */
    private $debug = false;

    /**
     * @Groups({"fsr_primary", "fsr_all", "singleRecordExecution"})
     * @ORM\Column(type="boolean", nullable=false, options={"default" = false})
     */
    private $singleRecordExecution = false;

    /**
     * @Groups({"fsr_primary", "fsr_all", "remoteExecutableFlag"})
     * @ORM\Column(type="boolean", nullable=false, options={"default" = false})
     */
    private $remoteExecutableFlag = false;

    /**
     * @Groups({"fsr_primary", "fsr_all", "parameters"})
     * @ORM\Column(type="jsonb", nullable=true)
     */
    private $parameters = [];

    /**
     * @Groups({"fsr_primary", "fsr_all", "synchronous"})
     * @ORM\Column(type="boolean", nullable=false, options={"default" = false})
     */
    private $synchronous = false;

    /**
     * @var \DateTime
     * @Groups({"fsr_primary", "fsr_all", "lastModifyDate"})
     * @ORM\Column(name="lastmodifydate", type="datetime", nullable=true)
     */
    private $lastModifyDate;

    /**
     * @Groups({"fsr_primary", "fsr_all", "collection"})
     * @ORM\ManyToOne(targetEntity=WorkflowCollection::class, inversedBy="workflows")
     * @ORM\JoinColumn(name="collection", referencedColumnName="uuid", nullable=true, onDelete="Cascade")
     * @ApiProperty(readableLink=false)
     */
    private $collection;

    /**
     * @Groups({"fsr_all", "versions"})
     * @ORM\OneToMany(targetEntity=WorkflowVersion::class, mappedBy="workflow", cascade={"persist", "remove"})
     */
    private $versions;

    /**
     * @ORM\ManyToOne(targetEntity="WorkflowStep", cascade={"detach"})
     * @ORM\JoinColumn(name="triggerstep_uuid", referencedColumnName="uuid", nullable=true)
     * @Groups({"fsr_primary", "fsr_all", "triggerStep"})
     * @ApiProperty(readableLink=false)
     */
    protected $triggerStep;

    /**
     * @Doctrine\ORM\Mapping\ManyToMany(targetEntity="WorkflowStep", orphanRemoval=true, cascade={"persist", "remove", "detach"})
     * @Doctrine\ORM\Mapping\JoinTable(name="workflow_workflowstep",
     *   joinColumns={
     *     @Doctrine\ORM\Mapping\JoinColumn(name="workflow_uuid", referencedColumnName="uuid", onDelete="CASCADE")
     *   },
     *   inverseJoinColumns={
     *     @Doctrine\ORM\Mapping\JoinColumn(name="workflowstep_uuid", referencedColumnName="uuid", onDelete="CASCADE")
     *   }
     * )
     * @ORM\OrderBy({"name" = "ASC"})
     * @Groups({"fsr_all", "steps"})
     */
    protected $steps;

    /**
     * @Doctrine\ORM\Mapping\ManyToMany(targetEntity="WorkflowRoute", cascade={"persist", "remove", "detach"}, orphanRemoval=true)
     * @Doctrine\ORM\Mapping\JoinTable(name="workflow_workflowroute",
     *   joinColumns={
     *     @Doctrine\ORM\Mapping\JoinColumn(name="workflow_uuid", referencedColumnName="uuid", onDelete="CASCADE")
     *   },
     *   inverseJoinColumns={
     *     @Doctrine\ORM\Mapping\JoinColumn(name="workflowroute_uuid", referencedColumnName="uuid", onDelete="CASCADE")
     *   }
     * )
     * @ORM\OrderBy({"name" = "ASC"})
     * @Groups({"fsr_all", "routes"})
     */
    protected $routes;

    /**
     * @Doctrine\ORM\Mapping\ManyToMany(targetEntity="WorkflowGroup", cascade={"persist", "remove", "detach"}, orphanRemoval=true)
     * @Doctrine\ORM\Mapping\JoinTable(name="workflow_workflowgroup",
     *   joinColumns={
     *     @Doctrine\ORM\Mapping\JoinColumn(name="workflow_uuid", referencedColumnName="uuid", onDelete="CASCADE")
     *   },
     *   inverseJoinColumns={
     *     @Doctrine\ORM\Mapping\JoinColumn(name="workflowgroup_uuid", referencedColumnName="uuid", onDelete="CASCADE")
     *   }
     * )
     * @ORM\OrderBy({"name" = "ASC"})
     * @Groups({"fsr_all", "groups"})
     */
    protected $groups;

    /**
     * @Doctrine\ORM\Mapping\ManyToOne(targetEntity="App\Entity\Core\Picklist", cascade={"persist"})
     * @Doctrine\ORM\Mapping\JoinColumns({
     *   @Doctrine\ORM\Mapping\JoinColumn(name="priority", referencedColumnName="uuid", onDelete="SET NULL")
     * })
     * @Groups({"fsr_primary", "fsr_all", "priority"})
     */
    protected $priority;

    /**
     * @Doctrine\ORM\Mapping\ManyToOne(targetEntity="App\Entity\Core\Picklist", cascade={"persist"})
     * @Doctrine\ORM\Mapping\JoinColumns({
     *   @Doctrine\ORM\Mapping\JoinColumn(name="playbook_origin", referencedColumnName="uuid", onDelete="SET NULL")
     * })
     * @Groups({"fsr_primary", "fsr_all", "playbookOrigin"})
     */
    protected $playbookOrigin;

    /**
     * @Groups({"fsr_primary", "fsr_all", "isEditable"})
     * @ORM\Column(type="boolean", nullable=true, options={"default" = true})
     */
    private $isEditable = true;

    public function __construct()
    {
        $this->steps = new ArrayCollection();
        $this->routes = new ArrayCollection();
        $this->groups = new ArrayCollection();
        $this->versions = new ArrayCollection();
    }


    public function getTriggerLimit(): ?int
    {
        return $this->triggerLimit;
    }

    public function setTriggerLimit(?int $triggerLimit): self
    {
        $this->triggerLimit = $triggerLimit;

        return $this;
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

    public function getAliasName(): ?string
    {
        return $this->aliasName;
    }

    public function setAliasName(?string $aliasName): self
    {
        $this->aliasName = $aliasName;

        return $this;
    }

    public function getTag(): ?string
    {
        return $this->tag;
    }

    public function setTag(?string $tag): self
    {
        $this->tag = $tag;

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

    public function getIsActive(): ?bool
    {
        return $this->isActive;
    }

    public function setIsActive(?bool $isActive): self
    {
        $this->isActive = $isActive;

        return $this;
    }

    public function getSingleRecordExecution(): ?bool
    {
        return $this->singleRecordExecution;
    }

    public function setSingleRecordExecution(?bool $singleRecordExecution): self
    {
        $this->singleRecordExecution = $singleRecordExecution;

        return $this;
    }

    public function getRemoteExecutableFlag(): ?bool
    {
        return $this->remoteExecutableFlag;
    }

    public function setRemoteExecutableFlag(?bool $remoteExecutableFlag): self
    {
        $this->remoteExecutableFlag = $remoteExecutableFlag;

        return $this;
    }

    public function getParameters(): ?array
    {
        return $this->parameters;
    }

    public function setParameters(?array $parameters): self
    {
        $this->parameters = $parameters;

        return $this;
    }

    public function getSynchronous(): ?bool
    {
        return $this->synchronous;
    }

    public function setSynchronous(?bool $synchronous): self
    {
        $this->synchronous = $synchronous;

        return $this;
    }

    public function getLastModifyDate(): ?\DateTimeInterface
    {
        return $this->lastModifyDate;
    }

    public function setLastModifyDate(?\DateTimeInterface $lastModifyDate): self
    {
        $this->lastModifyDate = $lastModifyDate;

        return $this;
    }

    public function getCollection(): ?WorkflowCollection
    {
        return $this->collection;
    }

    public function setCollection(?WorkflowCollection $collection): self
    {
        $this->collection = $collection;

        return $this;
    }

    /**
     * @return Collection|WorkflowVersion[]
     */
    public function getVersions(): ?Collection
    {
        if (array_key_exists('$versions', $_GET)) {
            return $this->versions;
        }
        return new ArrayCollection();
    }

    public function addVersion(WorkflowVersion $version): self
    {
        if (!$this->versions->contains($version)) {
            $this->versions[] = $version;
            $version->setWorkflow($this);
        }

        return $this;
    }

    public function removeVersion(WorkflowVersion $version): self
    {
        if ($this->versions->contains($version)) {
            $this->versions->removeElement($version);
            // set the owning side to null (unless already changed)
            if ($version->getWorkflow() === $this) {
                $version->setWorkflow(null);
            }
        }

        return $this;
    }

    /**
     * Set triggerStep
     *
     * @param \App\Entity\Workflow\WorkflowStep $triggerStep
     * 
     */
    public function setTriggerStep(\App\Entity\Workflow\WorkflowStep $triggerStep = null)
    {
        $this->triggerStep = $triggerStep;

        return $this;
    }

    /**
     * Get triggerStep
     *
     * @return \App\Entity\Workflow\WorkflowStep
     */
    public function getTriggerStep()
    {
        return $this->triggerStep;
    }

    /**
     * Add steps
     *
     * @param \App\Entity\Workflow\WorkflowStep $steps
     * @return Workflow
     */
    public function addStep(\App\Entity\Workflow\WorkflowStep $steps)
    {
        $this->steps[] = $steps;

        return $this;
    }

    /**
     * Remove steps
     *
     * @param \App\Entity\Workflow\WorkflowStep $steps
     */
    public function removeStep(\App\Entity\Workflow\WorkflowStep $steps)
    {
        $this->steps->removeElement($steps);
    }

    /**
     * Get steps
     *
     * @return \Doctrine\Common\Collections\Collection
     */
    public function getSteps()
    {
        if (array_key_exists('$triggerOnly', $_GET)) {
            return array($this->getTriggerStep());
        }
        return $this->steps;
    }

    /**
     * Add routes
     *
     * @param \App\Entity\Workflow\WorkflowRoute $routes
     * @return Workflow
     */
    public function addRoute(\App\Entity\Workflow\WorkflowRoute $routes)
    {
        $this->routes[] = $routes;

        return $this;
    }

    /**
     * Remove routes
     *
     * @param \App\Entity\Workflow\WorkflowRoute $routes
     */
    public function removeRoute(\App\Entity\Workflow\WorkflowRoute $routes)
    {
        $this->routes->removeElement($routes);
    }

    /**
     * Get routes
     *
     * @return \Doctrine\Common\Collections\Collection
     */
    public function getRoutes()
    {
        if (!array_key_exists('$triggerOnly', $_GET)) {
            return $this->routes;
        }
        return new ArrayCollection();
    }

    /**
     * Add group
     *
     * @param \App\Entity\Workflow\WorkflowGroup $routes
     * @return Workflow
     */
    public function addGroup(\App\Entity\Workflow\WorkflowGroup $group)
    {
        $this->groups[] = $group;

        return $this;
    }

    /**
     * Remove group
     *
     * @param \App\Entity\Workflow\WorkflowGroup $routes
     */
    public function removeGroup(\App\Entity\Workflow\WorkflowGroup $group)
    {
        $this->groups->removeElement($group);
    }

    /**
     * Get groups
     *
     * @return \Doctrine\Common\Collections\Collection
     */
    public function getGroups()
    {
        return $this->groups;
    }

    /**
     * Get priority
     */
    public function getPriority()
    {
        return $this->priority;
    }

    /**
     * Set priority
     *
     * @return  self
     */
    public function setPriority($priority)
    {
        $this->priority = $priority;

        return $this;
    }

    /**
     * Get the value of debug
     */
    public function getDebug()
    {
        return $this->debug;
    }

    /**
     * Set the value of debug
     *
     * @return  self
     */
    public function setDebug($debug)
    {
        $this->debug = $debug;

        return $this;
    }
    
    /**
     * Get playbookOrigin
     */
    public function getPlaybookOrigin()
    {
        return $this->playbookOrigin;
    }

    /**
     * Set playbookOrigin
     *
     * @return  self
     */
    public function setPlaybookOrigin($playbookOrigin)
    {
        $this->playbookOrigin = $playbookOrigin;

        return $this;
    }
    
    public function getIsEditable(): ?bool
    {
        return $this->isEditable;
    }

    public function setIsEditable(?bool $isEditable): self
    {
        $this->isEditable = $isEditable;

        return $this;
    }
}
