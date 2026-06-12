<script setup lang="ts">
import { computed } from 'vue'
import { VueFlow, type Edge, type Node, type NodeMouseEvent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { useWorkspace } from '../stores/useWorkspace'

const workspace = useWorkspace()

const nodes = computed<Node[]>(() =>
  workspace.pipeline.nodes.map((node, index) => ({
    id: node.id,
    label: `${node.stage}: ${node.label}`,
    position: { x: 90 + (index % 3) * 260, y: 70 + Math.floor(index / 3) * 150 },
    data: node,
    class: node.dataset_id === workspace.selectedDatasetId ? 'selected-node' : '',
  })),
)

const edges = computed<Edge[]>(() =>
  workspace.pipeline.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label || '',
    animated: true,
  })),
)

function onNodeClick(event: NodeMouseEvent) {
  workspace.selectedDatasetId = String(event.node.id)
}
</script>

<template>
  <div class="flow-wrap">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      fit-view-on-init
      class="pipeline-flow"
      @node-click="onNodeClick"
    >
      <Background />
      <Controls />
    </VueFlow>
  </div>
</template>
