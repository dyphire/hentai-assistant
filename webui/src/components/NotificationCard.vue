<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps({
  notification: {
    type: Object,
    required: true
  },
  isSaving: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['delete', 'save'])

const expanded = ref(false)
const originalNotification = ref(null as any)
const isDirty = ref(false)

// 可用事件列表
const availableEvents = [
  { key: 'task.complete', label: '任务完成', group: '任务' },
  { key: 'task.error', label: '任务失败', group: '任务' },
  { key: 'task.cancel', label: '任务取消', group: '任务' },
  { key: 'komga.new', label: '新书入库', group: 'Komga' },
  { key: 'komga.delete', label: '书籍删除', group: 'Komga' },
  { key: 'hath.offline', label: '客户端离线', group: 'H@H' },
  { key: 'hath.online', label: '客户端上线', group: 'H@H' },
  { key: 'hath.status_change', label: '状态变化', group: 'H@H' },
  { key: 'hath.unreachable', label: '网络不可达', group: 'H@H' }
]

// 按分组整理事件
const eventGroups = [
  { name: '任务', events: availableEvents.filter(e => e.group === '任务') },
  { name: 'Komga', events: availableEvents.filter(e => e.group === 'Komga') },
  { name: 'H@H', events: availableEvents.filter(e => e.group === 'H@H') }
]

import { watch, onMounted } from 'vue'

onMounted(() => {
  // Create a deep copy of the initial state for change detection
  originalNotification.value = JSON.parse(JSON.stringify(props.notification))
})

// Watch for changes in the notification object
watch(
  () => props.notification,
  (newValue) => {
    isDirty.value = JSON.stringify(newValue) !== JSON.stringify(originalNotification.value)
  },
  { deep: true }
)

function onSave() {
  emit('save')
  // After emitting save, update the original state to the new state
  // so the button becomes disabled again until further changes.
  originalNotification.value = JSON.parse(JSON.stringify(props.notification))
}

// 检查事件是否已选中
function isEventSelected(eventKey: string): boolean {
  return props.notification.events?.includes(eventKey) ?? false
}

// 切换事件选择状态
function toggleEvent(eventKey: string) {
  if (!props.notification.events) {
    props.notification.events = []
  }
  const index = props.notification.events.indexOf(eventKey)
  if (index === -1) {
    props.notification.events.push(eventKey)
  } else {
    props.notification.events.splice(index, 1)
  }
}
</script>

<template>
  <div class="config-section">
    <div class="card-header" @click="expanded = !expanded">
      <div class="header-content">
        <h2>{{ notification.name || 'Untitled Notifier' }}</h2>
        <div v-if="!expanded && (notification.type || notification.events?.length)" class="card-summary">
          <span v-if="notification.type" class="summary-badge type-badge">{{ notification.type }}</span>
          <span v-for="event in notification.events" :key="event" class="summary-badge event-badge">{{ event }}</span>
        </div>
      </div>
      <button class="toggle-btn" :class="{ 'is-expanded': expanded }"></button>
    </div>
    <div v-if="expanded" class="card-content">
      <div class="config-item">
        <label>启用:</label>
        <label class="switch">
          <input type="checkbox" v-model="notification.enable" />
          <span class="slider round"></span>
        </label>
      </div>
      <div class="config-item">
        <label>名称:</label>
        <input type="text" v-model="notification.name" />
      </div>
      <div class="config-item">
        <label>URL:</label>
        <input type="text" v-model="notification.url" />
      </div>
      <div class="config-item">
        <label>类型:</label>
        <select v-model="notification.type">
          <option value="apprise">Apprise</option>
          <option value="webhook">Webhook</option>
        </select>
      </div>
      <div class="config-item">
        <label>订阅事件:</label>
        <div class="event-groups">
          <div v-for="group in eventGroups" :key="group.name" class="event-group">
            <div class="event-group-title">{{ group.name }}</div>
            <div class="event-checkboxes">
              <label 
                v-for="event in group.events" 
                :key="event.key" 
                class="event-checkbox"
                :class="{ 'is-selected': isEventSelected(event.key) }"
              >
                <input 
                  type="checkbox" 
                  :checked="isEventSelected(event.key)"
                  @change="toggleEvent(event.key)"
                />
                <span class="checkbox-label">{{ event.label }}</span>
              </label>
            </div>
          </div>
        </div>
      </div>
      <div class="card-actions">
        <button @click="emit('delete')" class="delete-btn">删除</button>
        <button @click="onSave" class="save-btn" :disabled="!isDirty || isSaving">
          {{ isSaving ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.switch {
  position: relative;
  display: inline-block;
  width: 50px; /* Adjust size */
  height: 28px; /* Adjust size */
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: .4s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 20px; /* Adjust size */
  width: 20px; /* Adjust size */
  left: 4px;
  bottom: 4px;
  background-color: white;
  transition: .4s;
}

input:checked + .slider {
  background-color: #2196F3;
}

input:focus + .slider {
  box-shadow: 0 0 1px #2196F3;
}

input:checked + .slider:before {
  transform: translateX(22px); /* (width of switch - width of circle) - (padding * 2) = (50 - 20) - (4*2) = 22 */
}

.slider.round {
  border-radius: 28px; /* height */
}

.slider.round:before {
  border-radius: 50%;
}

/* Inherited styles from ConfigView.vue for consistency */
.config-section {
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
  border: 1px solid #e9ecef;
  border-radius: 12px;
  padding: 0; /* Remove padding to make header full-width */
  margin-bottom: 20px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07), 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
  width: 100%; /* Ensure card takes full width */
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start; /* Align to top */
  padding: 16px;
  cursor: pointer;
  border-bottom: 1px solid transparent; /* Add transparent border for transition */
}

.card-header:hover {
  background-color: rgba(0,0,0,0.02);
}

.card-content {
  padding: 16px;
  border-top: 1px solid #e9ecef;
}

h2 {
  color: #555;
  margin: 0;
  font-size: 1.25em;
  border: none;
  padding: 0;
}

.toggle-btn {
  background: none;
  border: none;
  border-radius: 50%; /* Make it a circle */
  cursor: pointer;
  color: #555;
  width: 50px; /* Fixed size */
  height: 30px; /* Fixed size */
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative; /* For pseudo-element positioning */
  transition: transform 0.2s ease, background-color 0.2s ease;
  flex-shrink: 0; /* Prevent shrinking */
}


.toggle-btn::after {
  content: '';
  display: block;
  width: 6px;
  height: 6px;
  border-bottom: 2px solid currentColor;
  border-right: 2px solid currentColor;
  transform: rotate(45deg); /* Pointing down */
  transition: transform 0.2s ease;
}

.toggle-btn.is-expanded::after {
  transform: rotate(-135deg); /* Pointing up */
}

.config-item {
  display: flex;
  flex-direction: column;
  align-items: stretch; /* Make children full width */
  margin-bottom: 16px;
  gap: 6px; /* Space between label and input */
}

.config-item label {
  font-weight: 600;
  color: #555;
  font-size: 14px;
  text-align: left;
}

.config-item input[type="text"],
.config-item select,
.event-tags {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  background-color: #ffffff;
  color: #333;
  transition: all 0.2s ease;
  min-height: 40px; /* Match height */
  box-sizing: border-box;
}

.config-item input[type="text"]:focus,
.config-item select:focus,
.event-tags:focus-within {
  border-color: #007bff;
  outline: none;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.15);
}

.event-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  background-color: #fafafa;
}

.event-group-title {
  font-size: 13px;
  font-weight: 600;
  color: #666;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #e9ecef;
}

.event-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.event-checkbox {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  background-color: white;
  cursor: pointer;
  font-size: 13px;
  color: #495057;
  transition: all 0.2s ease;
  user-select: none;
}

.event-checkbox:hover {
  border-color: #007bff;
  background-color: #f8f9ff;
}

.event-checkbox.is-selected {
  border-color: #007bff;
  background-color: #e7f1ff;
  color: #0056b3;
}

.event-checkbox input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: #007bff;
  cursor: pointer;
  margin: 0;
}

.checkbox-label {
  cursor: pointer;
}

/* Dark Mode for event checkboxes */
.dark .event-groups {
  background-color: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.15);
}

.dark .event-group-title {
  color: rgba(255, 255, 255, 0.7);
  border-bottom-color: rgba(255, 255, 255, 0.1);
}

.dark .event-checkbox {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.8);
}

.dark .event-checkbox:hover {
  border-color: var(--primary-color);
  background-color: rgba(0, 123, 255, 0.15);
}

.dark .event-checkbox.is-selected {
  border-color: var(--primary-color);
  background-color: rgba(0, 123, 255, 0.25);
  color: #fff;
}

/* Dark Mode */
.dark .config-section {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.05) 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.dark .card-header:hover {
  background-color: rgba(255,255,255,0.05);
}
.dark .card-content {
  border-top-color: rgba(255, 255, 255, 0.12);
}
.dark h2, .dark .config-item label, .dark .toggle-btn, .dark .events-tip {
  color: var(--text-color-light);
}
.dark .toggle-btn {
  border-color: rgba(255, 255, 255, 0.2);
  color: var(--text-color-light);
}

.dark .toggle-btn:hover {
  background-color: rgba(255, 255, 255, 0.1);
}
.dark .config-item input[type="text"],
.dark .config-item select,
.dark .event-tags {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
  color: var(--text-color-light);
}
.dark .config-item input[type="text"]:focus,
.dark .config-item select:focus,
.dark .event-tags:focus-within {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
  background-color: rgba(255, 255, 255, 0.1);
}
.dark .tag {
  background-color: var(--primary-color);
}

.card-actions {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #e9ecef;
  display: flex;
  justify-content: flex-end;
  gap: 10px; /* Add space between buttons */
}

.delete-btn, .save-btn {
  color: white;
  border: none;
  border-radius: 5px;
  padding: 8px 15px;
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

.delete-btn {
  background-color: #dc3545;
}
.delete-btn:hover {
  background-color: #c82333;
}

.save-btn {
  background-color: #007bff;
}
.save-btn:hover {
  background-color: #0056b3;
}

.save-btn:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.dark .card-actions {
  border-top-color: rgba(255, 255, 255, 0.12);
}

.header-content {
  display: flex;
  flex-direction: column;
  gap: 8px; /* Space between title and summary */
  flex-grow: 1; /* Allow content to take available space */
  padding-right: 16px; /* Space before the button */
}

.card-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.summary-badge {
  padding: 2px 8px;
  border-radius: 12px; /* Pill shape */
  font-size: 12px;
  font-weight: 500;
  border: 1px solid transparent;
}

.type-badge {
  background-color: #e0e7ff;
  color: #4338ca;
  border-color: #c7d2fe;
}

.event-badge {
  background-color: #e2e8f0;
  color: #475569;
  border-color: #cbd5e1;
}

.dark .type-badge {
  background-color: #3730a3;
  color: #e0e7ff;
  border-color: #4f46e5;
}

.dark .event-badge {
  background-color: #475569;
  color: #e2e8f0;
  border-color: #64748b;
}
</style>