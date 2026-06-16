<script setup lang="ts">
import { Activity, BarChart3, Database, GitBranch, ShieldCheck, TableProperties, Upload } from 'lucide-vue-next'
import { useWorkspace } from '../stores/useWorkspace'

const workspace = useWorkspace()

function onUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) workspace.upload(file)
}
</script>

<template>
  <div class="brand">
    <div class="brand-mark">AD</div>
    <div>
      <strong>Agentic DataLab</strong>
      <span>Enterprise Console</span>
    </div>
  </div>

  <label class="upload-box">
    <Upload :size="18" />
    <span>Upload CSV / Excel / Parquet</span>
    <input type="file" accept=".csv,.txt,.xlsx,.xls,.parquet" @change="onUpload" />
  </label>

  <div class="field">
    <label>Tenant</label>
    <input v-model="workspace.settings.tenant_id" />
  </div>

  <div class="field">
    <label>User</label>
    <input v-model="workspace.settings.user_id" />
  </div>

  <div class="field">
    <label>Model</label>
    <input v-model="workspace.settings.model" placeholder="vLLM default" />
  </div>

  <div class="switch-row">
    <ShieldCheck :size="17" />
    <label>
      <input v-model="workspace.settings.require_human_approval" type="checkbox" />
      HITL for risky tools
    </label>
  </div>

  <div class="switch-row">
    <label>
      <input v-model="workspace.settings.mlflow_enabled" type="checkbox" />
      MLflow logging
    </label>
  </div>

  <div class="switch-row">
    <label>
      <input v-model="workspace.settings.h2o_enabled" type="checkbox" />
      H2O AutoML
    </label>
  </div>

  <section class="workflow-section">
    <div class="section-title">Workflows</div>
    <label class="target-picker">
      <span>Target</span>
      <select v-model="workspace.targetColumn" :disabled="!workspace.targetOptions.length || workspace.busy">
        <option value="">auto / none</option>
        <option v-for="column in workspace.targetOptions" :key="column" :value="column">
          {{ column }}
        </option>
      </select>
    </label>

    <div class="workflow-grid">
      <button type="button" title="EDA" :disabled="workspace.busy || !workspace.selectedDatasetId" @click="workspace.runWorkflow('eda')">
        <Activity :size="15" />
        EDA
      </button>
      <button type="button" title="Charts" :disabled="workspace.busy || !workspace.selectedDatasetId" @click="workspace.runWorkflow('charts')">
        <BarChart3 :size="15" />
        Charts
      </button>
      <button type="button" title="Features" :disabled="workspace.busy || !workspace.selectedDatasetId" @click="workspace.runWorkflow('features')">
        <TableProperties :size="15" />
        Features
      </button>
      <button type="button" title="Classification" :disabled="workspace.busy || !workspace.selectedDatasetId" @click="workspace.runWorkflow('classification')">
        <GitBranch :size="15" />
        Classify
      </button>
      <button type="button" title="Regression" :disabled="workspace.busy || !workspace.selectedDatasetId" @click="workspace.runWorkflow('regression')">
        <GitBranch :size="15" />
        Regress
      </button>
      <button type="button" title="Clustering" :disabled="workspace.busy || !workspace.selectedDatasetId" @click="workspace.runWorkflow('clustering')">
        <Database :size="15" />
        Cluster
      </button>
      <button type="button" title="Anomaly Detection" :disabled="workspace.busy || !workspace.selectedDatasetId" @click="workspace.runWorkflow('anomaly')">
        <Activity :size="15" />
        Anomaly
      </button>
      <button type="button" title="MLflow" :disabled="workspace.busy || !workspace.selectedDatasetId" @click="workspace.runWorkflow('mlflow')">
        <Database :size="15" />
        MLflow
      </button>
    </div>
  </section>

  <div class="dataset-list">
    <h2>Datasets</h2>
    <button
      v-for="dataset in workspace.datasets"
      :key="dataset.id"
      class="dataset-item"
      :class="{ active: workspace.selectedDatasetId === dataset.id }"
      @click="workspace.selectDataset(dataset.id)"
    >
      <strong>{{ dataset.label }}</strong>
      <span>{{ dataset.stage }} · {{ dataset.shape[0] }} x {{ dataset.shape[1] }}</span>
    </button>
  </div>

  <p v-if="workspace.error" class="error">{{ workspace.error }}</p>
</template>
