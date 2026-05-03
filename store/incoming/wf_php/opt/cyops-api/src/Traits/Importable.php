<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Traits;

use Symfony\Component\Serializer\Annotation\Groups;

trait Importable
{

    /**
     * @Groups({"fsr_primary", "fsr_all", "importedBy"})
     * @ORM\Column(type="json", nullable=true)
     */
    protected $importedBy = [];

    /**
     * Get the value of importedBy
     */
    public function getImportedBy()
    {
        return $this->importedBy;
    }

    /**
     * Set the value of importedBy
     *
     * @return  self
     */
    public function setImportedBy($importedBy = [])
    {
        $this->importedBy = $importedBy;

        return $this;
    }
}
