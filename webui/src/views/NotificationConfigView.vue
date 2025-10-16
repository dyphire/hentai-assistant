<script setup lang="ts">
import { ref, onMounted } from 'vue'
import NotificationCard from '@/components/NotificationCard.vue'

import axios from 'axios'

const notifications = ref<any[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const saveSuccess = ref(false)
const saveError = ref<string | null>(null)

async function fetchNotifications() {
  loading.value = true
  error.value = null
  try {
    const response = await axios.get('/api/config')
    const notificationConfig = response.data.notification || {}
    
    // Convert the dictionary to an array for v-for, preserving the key
    notifications.value = Object.entries(notificationConfig)
      .filter(([key]) => key !== 'enable') // Exclude the global enable flag
      .map(([key, value]) => ({
        key: key, // This is the original dictionary key, e.g., 'my_notifier'
        ...(value as object),
        isSaving: false,
      }))
  } catch (err) {
    error.value = '无法加载通知配置。'
    console.error(err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchNotifications()
})

function addNotifier() {
  // Generate a unique key for the new notifier
  const newKey = `notifier_${Date.now()}`
  notifications.value.push({
    key: newKey,
    name: 'New Notifier',
    url: '',
    type: 'apprise',
    events: [],
    enable: false, // Default to disabled
    isSaving: false,
  })
}

async function removeNotifier(key: string) {
  const notifier = notifications.value.find(n => n.key === key)
  if (!notifier) return;

  if (window.confirm(`您确定要删除通知器 "${notifier.name}" 吗？`)) {
    notifier.isSaving = true
    saveSuccess.value = false
    saveError.value = null
    try {
      const currentConfig = (await axios.get('/api/config')).data
      const backendNotifiers = currentConfig.notification || {}

      // Delete the notifier by its key
      delete backendNotifiers[key]

      const updatedConfig = {
        ...currentConfig,
        notification: backendNotifiers,
      }
      await axios.post('/api/config?source=notification', updatedConfig)
      
      // On success, remove from the local UI state
      notifications.value = notifications.value.filter(n => n.key !== key)
      saveSuccess.value = true
      setTimeout(() => (saveSuccess.value = false), 3000)

    } catch (err) {
      saveError.value = `删除 '${notifier.name}' 失败。`
      console.error(err)
      notifier.isSaving = false
    }
  }
}

async function saveNotifier(key: string) {
  const notifier = notifications.value.find(n => n.key === key);
  if (!notifier) return;

  notifier.isSaving = true
  saveSuccess.value = false
  saveError.value = null
  try {
    const currentConfig = (await axios.get('/api/config')).data
    const backendNotifiers = currentConfig.notification || {}

    // Clean the local notifier of its UI state before saving
    const { isSaving, key: notifierKey, ...localNotifierToSave } = notifier;

    // Add/update the notifier in the backend dictionary using its key
    backendNotifiers[notifierKey] = localNotifierToSave

    const updatedConfig = {
      ...currentConfig,
      notification: backendNotifiers,
    }

    await axios.post('/api/config?source=notification', updatedConfig)

    saveSuccess.value = true
    setTimeout(() => (saveSuccess.value = false), 3000)
    
  } catch (err) {
    saveError.value = `保存 '${notifier.name}' 失败。`
    console.error(err)
  } finally {
    if (notifier) {
      notifier.isSaving = false
    }
  }
}
</script>

<template>
  <div class="notification-config">
    <div v-if="loading">加载中...</div>
    <div v-else-if="error" class="error-message">{{ error }}</div>
    <div v-else>
      <div v-for="notification in notifications" :key="notification.key" class="notification-card-wrapper">
        <NotificationCard
          :notification="notification"
          :is-saving="notification.isSaving"
          @delete="removeNotifier(notification.key)"
          @save="saveNotifier(notification.key)"
        />
      </div>
       <div class="controls">
        <button @click="addNotifier" class="add-btn">添加通知器</button>
       </div>
    </div>
    <!-- Global Save Section Removed -->
    <div class="feedback-section">
        <div v-if="saveSuccess" class="success-message">配置已成功保存！</div>
        <div v-if="saveError" class="error-message">{{ saveError }}</div>
    </div>
  </div>
</template>

<style scoped>
/* Using styles from ConfigView.vue for consistency */
.notification-config {
  /* No extra padding needed */
}

.notification-card-wrapper {
  display: flex;
  align-items: flex-start; /* Align to the top */
  gap: 16px;
  margin-bottom: 20px;
}

.controls {
  margin-top: 20px;
}

button {
  display: inline-block;
  padding: 10px 15px;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 5px;
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

button:hover {
  background-color: #0056b3;
}

.add-btn {
  background-color: #28a745;
}
.add-btn:hover {
  background-color: #218838;
}

.feedback-section {
  margin-top: 20px;
  text-align: center;
}


/* Inherited from ConfigView */
.error-message {
  color: #dc3545;
  background-color: #f8d7da;
  border: 1px solid #f5c6cb;
  padding: 10px;
  border-radius: 5px;
  margin-top: 15px;
  text-align: center;
}

.success-message {
  color: #28a745;
  background-color: #d4edda;
  border: 1px solid #c3e6cb;
  padding: 10px;
  border-radius: 5px;
  margin-top: 15px;
  text-align: center;
}

/* Dark mode */
.dark .feedback-section {
  /* No specific styles needed unless you want a border */
}

.dark .error-message {
  background-color: rgba(220, 53, 69, 0.1);
  border-color: var(--danger-color);
  color: var(--danger-color);
}

.dark .success-message {
  background-color: rgba(40, 167, 69, 0.1);
  border-color: var(--success-color);
  color: var(--success-color);
}
</style>