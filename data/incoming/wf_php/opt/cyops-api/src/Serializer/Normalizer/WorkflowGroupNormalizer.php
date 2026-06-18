<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Serializer\Normalizer;

use App\Entity\Workflow\WorkflowGroup;

final class WorkflowGroupNormalizer extends EfficientItemNormalizer
{
    
    public function normalize($object, $format = null, array $context = [])
    {
        $context["group"] = ["fsr_primary"];
        if (array_key_exists("object_class", $context)) {
            $context["relationships"] = false;
        }
        return parent::normalize($object, $format, $context);
    }

    public function supportsNormalization($data, $format = null, array $context = []): bool
    {
        return 'jsonld' === $format && $data instanceof WorkflowGroup;
    }

    /**
     * {@inheritdoc}
     */
    public function supportsDenormalization($data, $type, $format = null, array $context = [])
    {
        return false;
    }
}
