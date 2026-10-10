<template>
  <div class="extensions-view extension-page-root">
    <ViewSwitchHeader
      v-model:active-key="activeTab"
      title="Extension Management"
      :items="extensionTabs"
      aria-label="Extension management tabs"
    >
      <template #actions>
        <!-- Manual ingestion features (Add, Upload, Remote Install) are disabled as per engineering directive -->
      </template>
    </ViewSwitchHeader>

    <div class="extensions-content">
      <div v-show="activeTab === 'tools'" class="tab-panel">
        <ToolsManagerComponent />
      </div>
      <div v-show="activeTab === 'skills'" class="tab-panel">
        <SkillsManagerComponent ref="skillsRef" @import="handleSkillsImport" />
      </div>
      <div v-show="activeTab === 'mcp'" class="tab-panel">
        <McpServersComponent ref="mcpRef" @add="handleMcpAdd" />
      </div>
      <div v-show="activeTab === 'subagents'" class="tab-panel">
        <SubAgentsComponent ref="subagentsRef" @add="handleSubagentAdd" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import SkillsManagerComponent from '@/components/SkillsManagerComponent.vue'
import ToolsManagerComponent from '@/components/ToolsManagerComponent.vue'
import McpServersComponent from '@/components/McpServersComponent.vue'
import SubAgentsComponent from '@/components/SubAgentsComponent.vue'
import ViewSwitchHeader from '@/components/ViewSwitchHeader.vue'

const route = useRoute()
const activeTab = ref('tools')
const skillsRef = ref(null)
const mcpRef = ref(null)
const subagentsRef = ref(null)

const extensionTabs = [
  { key: 'tools', label: 'Tools' },
  { key: 'mcp', label: 'MCP' },
  { key: 'subagents', label: 'Subagents' },
  { key: 'skills', label: 'Skills' }
]

watch(
  () => route.query,
  (query) => {
    if (query.tab && ['tools', 'skills', 'mcp', 'subagents'].includes(query.tab)) {
      activeTab.value = query.tab
    }
  },
  { immediate: true }
)

const handleSkillsImport = () => {
  handleSkillsRefresh()
}

const handleSkillsRefresh = () => {
  if (skillsRef.value?.fetchSkills) {
    skillsRef.value.fetchSkills()
  }
}

const handleMcpAdd = () => {
  if (mcpRef.value?.showAddModal) {
    mcpRef.value.showAddModal()
  }
}

const handleSubagentAdd = () => {
  if (subagentsRef.value?.showAddModal) {
    subagentsRef.value.showAddModal()
  }
}

</script>

<style scoped lang="less">
@import '@/assets/css/extensions.less';

.extensions-view {
  .extension-header-actions {
    display: flex;
    gap: 8px;
  }

  .extensions-content {
    flex: 1;
    min-height: 0;
    overflow: hidden;

    .tab-panel {
      height: 100%;
      min-height: 0;
      overflow: hidden;
    }
  }
}

@media (max-width: 768px) {
  :global(.app-layout:has(.extensions-view)) {
    min-width: 0;
  }

  .extensions-view {
    min-width: 0;

    :deep(.header-container) {
      height: auto;
      flex-shrink: 0;
      padding: 8px 12px;
    }

    :deep(.header-title-block) {
      flex-direction: column;
      align-items: flex-start;
      gap: 4px;
    }

    :deep(.view-switcher) {
      flex-wrap: wrap;
      padding-left: 0;
      margin-left: 0;
      border-left: 0;
    }

    :deep(.switcher-item) {
      min-height: 44px;
    }

    :deep(.layout-wrapper) {
      flex-direction: column;
    }

    :deep(.sidebar-list) {
      width: 100%;
      flex: 0 0 30%;
      min-height: 140px;
      max-height: 260px;
      border-right: 0;
      border-bottom: 1px solid var(--gray-150);
    }

    :deep(.sidebar-tool) {
      width: 44px;
      height: 44px;
    }

    :deep(.main-panel) {
      min-width: 0;
      min-height: 0;
    }

    :deep(.panel-top-bar) {
      flex-wrap: wrap;
      gap: 8px;
      padding: 12px;
    }

    :deep(.panel-title-stack),
    :deep(.title-text-group) {
      min-width: 0;
      overflow-wrap: anywhere;
    }

    :deep(.detail-section-container) {
      padding: 12px;
    }
  }
}

@media (max-width: 768px) and (max-height: 480px) {
  .extensions-view {
    overflow-y: auto;

    .extensions-content {
      flex: 0 0 480px;
      height: 480px;
      min-height: 480px;
    }

    :deep(.layout-wrapper) {
      flex: 0 0 auto;
      height: 480px;
      min-height: 480px;
    }

    :deep(.sidebar-list) {
      flex-basis: 140px;
    }

    :deep(.main-panel) {
      min-height: 340px;
    }
  }
}
</style>
