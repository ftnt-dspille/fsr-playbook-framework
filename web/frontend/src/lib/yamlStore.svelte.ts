/**
 * Editor buffer — lives outside the Author component so it survives
 * navigation to /run, /browse, /history.
 */

const PLACEHOLDER = `# Welcome — try one of these to get started:
#   1. Edit this YAML and watch the right-rail Diagnostics update live.
#   2. Ask the chat: "build a hello-world playbook with one set_variable step"
#   3. Click Compile to see structured errors. Push/Run need a live FSR (.env).

collection: Hello World
playbooks:
  - name: Hello
    steps:
      - id: trigger
        type: start
        next: stop
      - id: stop
        type: stop
`;

class YamlStore {
  text = $state<string>(PLACEHOLDER);

  reset() {
    this.text = PLACEHOLDER;
  }
}

export const yamlStore = new YamlStore();
