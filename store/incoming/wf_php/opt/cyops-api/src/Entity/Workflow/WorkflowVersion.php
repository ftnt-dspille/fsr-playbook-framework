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
use App\Traits\Trackable;
use Doctrine\ORM\Mapping as ORM;
use Symfony\Component\Serializer\Annotation\Groups;

/**
 *  @ApiResource(
 *     attributes={"validation_groups"={"fsr_primary", "fsr_all"}, "fsr_type"="workflow_versions", "fsr_module"="workflows", "fsr_singular"="workflow_version"},
 *     denormalizationContext={"groups"={"fsr_all", "password"}, "fetch_data"=false, "fsr_type"="workflow_versions"},
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
 * @ORM\Entity()
 * @ORM\Table(name="workflow_versions")
 */
class WorkflowVersion extends BaseEntity
{

    use Indexable;
    use Trackable;
    
    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="string", nullable=true)
     */
    private $note;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="jsonb", nullable=true)
     */
    private $json = [];

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\Column(type="boolean", nullable=false , options={"default" = false})
     */
    private $autosave = false;

    /**
     * @Groups({"fsr_primary", "fsr_all"})
     * @ORM\ManyToOne(targetEntity=Workflow::class, inversedBy="versions")
     */
    private $workflow;

    public function getId(): ?int
    {
        return $this->id;
    }

    public function getNote(): ?string
    {
        return $this->note;
    }

    public function setNote(?string $note): self
    {
        $this->note = $note;

        return $this;
    }

    public function getJson()
    {
        if (array_key_exists('$includeData', $_GET)) {
            return $this->json;
        }
    }

    public function setJson($json): self
    {
        $this->json = $json;

        return $this;
    }

    public function getAutosave(): ?bool
    {
        return $this->autosave;
    }

    public function setAutosave(?bool $autosave): self
    {
        $this->autosave = $autosave;

        return $this;
    }

    public function getWorkflow(): ?Workflow
    {
        return $this->workflow;
    }

    public function setWorkflow(?Workflow $workflow): self
    {
        $this->workflow = $workflow;

        return $this;
    }
}
