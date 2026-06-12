<script setup lang="ts">
import { Upload, ShieldCheck } from 'lucide-vue-next'
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

  <div class="dataset-list">
    <h2>Datasets</h2>
    <button
      v-for="dataset in workspace.datasets"
      :key="dataset.id"
      class="dataset-item"
      :class="{ active: workspace.selectedDatasetId === dataset.id }"
      @click="workspace.selectedDatasetId = dataset.id"
    >
      <strong>{{ dataset.label }}</strong>
      <span>{{ dataset.stage }} · {{ dataset.shape[0] }} × {{ dataset.shape[1] }}</span>
    </button>
  </div>

  <p v-if="workspace.error" class="error">{{ workspace.error }}</p>
</template>

