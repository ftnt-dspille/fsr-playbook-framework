<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Entity\Core;

use DateTime;
use App\Entity\Base\BaseEntity;
use Doctrine\ORM\Mapping as ORM;
use App\Entity\Core\SolutionPack;
use App\Repository\ImportJobRepository;
use ApiPlatform\Core\Annotation\ApiResource;
use Symfony\Component\Serializer\Annotation\Groups;

/**
 *  @ApiResource(
 *     attributes={"validation_groups"={"fsr_primary", "fsr_all"}, "fsr_type"="import_jobs", "fsr_module"="security", "fsr_singular"="Import Job"},
 *     denormalizationContext={"groups"={"fsr_all", "password"}, "fetch_data"=false, "fsr_type"="import_jobs"},
 *     normalizationContext={"circular_reference_limit"=2},
 *     collectionOperations={
 *          "get" = { "security_post_denormalize" = "is_granted('read.security', object)" },
 *          "post" = { "security_post_denormalize" = "is_granted('create.security', object)" }
 *     },
 *     itemOperations={
 *          "get" = { "security" = "is_granted('read.security', object)" },
 *          "put" = { "security" = "is_granted('update.security', object)" },
 *          "delete" = { "security" = "is_granted('delete.security', object)" }
 *     }
 * )
 * @ORM\Entity(repositoryClass=ImportJobRepository::class)
 * @Doctrine\ORM\Mapping\Table(name="import_jobs", indexes={@Doctrine\ORM\Mapping\Index(name="import_jobs_search_idx", columns={"modifydate"}), @Doctrine\ORM\Mapping\Index(name="import_jobs_id_search_idx", columns={"id"})})
 */
class ImportJob extends BaseEntity
{

    use \App\Traits\Indexable;
    use \App\Traits\Trackable;

    /**
     * @Groups({"fsr_primary", "fsr_all", "file"})
     * @ORM\Column(type="text", nullable=true)
     */
    private $file;

    /**
     * @Groups({"fsr_primary", "fsr_all", "status"})
     * @ORM\Column(type="string", length=255, nullable=true)
     */
    private $status;

    /**
     * @Groups({"fsr_primary", "fsr_all", "errorMessage"})
     * @ORM\Column(type="text", nullable=true)
     */
    private $errorMessage = '';

    /**
     * @Groups({"fsr_primary", "fsr_all", "logMessages"})
     * @ORM\Column(type="array", nullable=true)
     */
    private $logMessages = [];

    /**
     * @Groups({"fsr_primary", "fsr_all", "progressPercent"})
     * @ORM\Column(type="integer", nullable=false)
     */
    private $progressPercent = 0;

    /**
     * @Groups({"fsr_primary", "fsr_all", "currentlyImporting"})
     * @ORM\Column(type="string", length=1024, nullable=true)
     */
    private $currentlyImporting;

    /**
     * @Groups({"fsr_primary", "fsr_all", "options"})
     * @ORM\Column(type="jsonb", nullable=true)
     */
    private $options = [];

    /**
     * @Groups({"fsr_primary", "fsr_all", "type"})
     * @ORM\Column(type="string", length=255, nullable=true)
     */
    private $type = 'Import Wizard';

    /**
     * @Groups({"fsr_primary", "fsr_all", "solutionPack"})
     * @ORM\OneToOne(targetEntity="\App\Entity\Core\SolutionPack", mappedBy="importJob",cascade={"persist"})
     */
    private $solutionPack;


    public function getFile(): ?string
    {
        return $this->file;
    }

    public function setFile(?string $file): self
    {
        $this->file = $file;

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

    public function getType(): ?string
    {
        return $this->type;
    }

    public function setType(?string $type): self
    {
        $this->type = $type;

        return $this;
    }

    public function getErrorMessage(): ?string
    {
        return $this->errorMessage;
    }

    public function setErrorMessage(?string $errorMessage): self
    {
        $this->errorMessage = $errorMessage;

        return $this;
    }

    public function getProgressPercent(): ?int
    {
        return $this->progressPercent;
    }

    public function setProgressPercent(?int $progressPercent): self
    {
        $this->progressPercent = $progressPercent;

        return $this;
    }

    public function getCurrentlyImporting(): ?string
    {
        return $this->currentlyImporting;
    }

    public function setCurrentlyImporting(?string $currentlyImporting): self
    {
        $this->currentlyImporting = $currentlyImporting;

        return $this;
    }

    public function getOptions(): ?array
    {
        return $this->options;
    }

    public function setOptions(?array $options): self
    {
        $this->options = $options;

        return $this;
    }

    public function getSolutionPack()
    {
        return $this->solutionPack;
    }

    public function setSolutionPack(SolutionPack $solutionPack = null): self
    {
        $this->solutionPack = $solutionPack;
        return $this;
    }

    public function getLogMessages(): ?array
    {
        return $this->logMessages;
    }

    public function addLogMessage(?string $logMessage)
    {
        $dateTime = new DateTime();
        $this->logMessages[] = [
            'message' => $logMessage,
            'date' => $dateTime->getTimestamp()
        ];

        return $this;
    }

    public function clearLogMessages()
    {
        $this->logMessages = [];

        return $this;
    }
}
