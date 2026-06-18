<?php
/* Copyright start
  Copyright (C) 2008 - 2025 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end */

namespace App\Serializer\Normalizer;

use App\Entity\Workflow\Workflow;
use App\Entity\Workflow\WorkflowRoute;
use App\Entity\Workflow\WorkflowStep;
use App\Entity\Workflow\WorkflowStepType;

final class WorkflowNormalizer extends EfficientItemNormalizer
{
    public function normalize($object, $format = null, array $context = [])
    {
        $context['ignore_depth'] = true;
        if ($object instanceof Workflow && isset($context['object_class'])) {
            unset($context['object_class']);
        }
        unset($context['groups']);
        return parent::normalize($object, $format, $context);
    }

    public function supportsNormalization($data, $format = null, array $context = []): bool
    {
        return 'jsonld' === $format &&
            ($data instanceof Workflow || $data instanceof WorkflowStep || $data instanceof WorkflowRoute || $data instanceof WorkflowStepType);
    }

    /**
     * {@inheritdoc}
     */
    public function supportsDenormalization($data, $type, $format = null, array $context = [])
    {
        return false;
    }
}
