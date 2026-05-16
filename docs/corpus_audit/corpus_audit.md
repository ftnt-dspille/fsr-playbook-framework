# Corpus shape audit

## Step argument keys vs resolver whitelists

### `ManualInput` — 190 rows, 27 distinct keys
✓ no unexpected keys

## ManualInput inputVariables tuple drift

Distinct tuples: 20

**Uncovered tuples** (no friendly `kind:` projects to them):
- formType='text' dataType='text' type='string' templateUrl=None ×48
- formType='textarea' dataType='text' type='string' templateUrl='app/components/form/fields/json.html' ×11
- formType='text' dataType='text' type='string' templateUrl='app/components/form/fields/integer.html' ×2
- formType='textarea' dataType='text' type='string' templateUrl='app/components/form/fields/input.html' ×1
- formType='text' dataType='text' type='string' templateUrl='app/components/form/fields/checkbox.html' ×1
- formType='text' dataType='text' type='string' templateUrl='app/components/form/fields/json.html' ×1

Kinds never observed in corpus: `date`, `datetime`, `decimal`, `email`, `filehash`, `image`, `integer`, `multiselect`, `multiselectpicklist`, `phone`, `url`
