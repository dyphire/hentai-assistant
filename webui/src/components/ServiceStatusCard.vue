<template>
  <div class="status-section">
    <div v-if="loading">加载中...</div>
    <div v-else-if="error" class="error-message">{{ error }}</div>
    <div v-else class="status-grid">
      <div class="status-item">
        <div class="service-info">
          <span class="service-name">E-Hentai</span>
          <span class="service-details" v-if="status.eh_funds">
            <span v-if="formattedGP">GP: {{ formattedGP }}k</span>
            <span v-if="formattedCredits"> | Cr: {{ formattedCredits }}</span>
          </span>
        </div>
        <span
          class="status-badge"
          :class="[ehentaiStatusClass(), { 'clickable': isEhentaiRestricted(), 'refreshing': refreshing }]"
          @click="handleEhentaiClick"
          :title="isEhentaiRestricted() ? '点击刷新 Cookie' : ''"
        >
          <span v-if="refreshing" class="spinner"></span>
          <span v-else>{{ ehentaiStatusText() }}</span>
        </span>
      </div>
      <div class="status-item">
        <span class="service-name">NHentai</span>
        <span class="status-badge" :class="nhentaiStatusClass()">{{ nhentaiStatusText() }}</span>
      </div>
      <div class="status-item">
        <span class="service-name">Aria2</span>
        <span class="status-badge" :class="statusClass(status.aria2_toggle)">{{ statusText(status.aria2_toggle) }}</span>
      </div>
      <div class="status-item">
        <div class="service-info">
          <span class="service-name">Komga</span>
          <span class="service-details" v-if="status.komga_toggle && !status.notification_toggle">SSE 监听器异常</span>
          <span class="service-details" v-else-if="status.komga_toggle && status.notification_pid">SSE PID: {{ status.notification_pid }}</span>
        </div>
        <span class="status-badge" :class="komgaStatusClass()">{{ komgaStatusText() }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import axios from 'axios';

interface ConfigStatus {
  eh_valid: boolean | null;
  exh_valid: boolean | null;
  nh_toggle: boolean | null;
  aria2_toggle: boolean;
  komga_toggle: boolean;
  notification_toggle: boolean;
  notification_pid?: number;
  eh_funds?: {
    GP: number | string;
    Credits: number | string;
  };
}

const status = ref<ConfigStatus>({
    eh_valid: false,
    exh_valid: false,
    nh_toggle: null,
    aria2_toggle: false,
    komga_toggle: false,
    notification_toggle: false,
});
const loading = ref(true);
const error = ref<string | null>(null);
const refreshing = ref(false);

const API_BASE_URL = '/api';

// 格式化数字，添加千分符
const formatNumber = (value: number | string): string => {
  if (value === undefined || value === null) return '0';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '0';
  return num.toLocaleString('en-US');
};

// 计算格式化后的 GP 和 Credits
const formattedGP = computed(() => {
  if (status.value.eh_funds?.GP !== undefined) {
    return formatNumber(status.value.eh_funds.GP);
  }
  return null;
});

const formattedCredits = computed(() => {
  if (status.value.eh_funds?.Credits !== undefined) {
    return formatNumber(status.value.eh_funds.Credits);
  }
  return null;
});

const fetchStatus = async () => {
  loading.value = true;
  error.value = null;
  try {
    const response = await axios.get(`${API_BASE_URL}/config`);
    status.value = response.data.status;
  } catch (err) {
    error.value = '无法加载服务状态。';
    console.error(err);
  } finally {
    loading.value = false;
  }
};

const statusClass = (s: boolean) => {
  return s ? 'status-success' : 'status-error';
};

const statusText = (s: boolean) => {
  return s ? '正常' : '异常';
};

const ehentaiStatusClass = () => {
  if (status.value.exh_valid === true) {
    return 'status-success';
  }
  if (status.value.eh_valid === null && status.value.exh_valid === null) {
    return 'status-error';
  }
  return 'status-warning';
};

const ehentaiStatusText = () => {
  if (status.value.exh_valid === true) {
    return '正常';
  }
  if (status.value.eh_valid === null && status.value.exh_valid === null) {
    return '异常';
  }
  return '受限';
};

const isEhentaiRestricted = () => {
  return ehentaiStatusClass() === 'status-warning';
};

const handleEhentaiClick = async () => {
  if (!isEhentaiRestricted() || refreshing.value) {
    return;
  }
  
  refreshing.value = true;
  try {
    const response = await axios.get(`${API_BASE_URL}/ehentai/refresh`);
    if (response.data.eh_valid !== undefined) {
      status.value.eh_valid = response.data.eh_valid;
      status.value.exh_valid = response.data.exh_valid;
      if (response.data.funds) {
        status.value.eh_funds = response.data.funds;
      }
    }
  } catch (err) {
    console.error('刷新 E-Hentai Cookie 失败:', err);
    error.value = '刷新失败，请稍后重试';
    setTimeout(() => {
      error.value = null;
    }, 3000);
  } finally {
    refreshing.value = false;
  }
};

const nhentaiStatusClass = () => {
  if (status.value.nh_toggle === true) {
    return 'status-success';
  }
  if (status.value.nh_toggle === false) {
    return 'status-warning';
  }
  return 'status-error';
};

const nhentaiStatusText = () => {
  if (status.value.nh_toggle === true) {
    return '正常';
  }
  if (status.value.nh_toggle === false) {
    return '受限';
  }
  return '异常';
};

const komgaStatusClass = () => {
  if (!status.value.komga_toggle) {
    return 'status-error';
  }
  if (!status.value.notification_toggle) {
    return 'status-warning';
  }
  return 'status-success';
};

const komgaStatusText = () => {
  if (!status.value.komga_toggle) {
    return '异常';
  }
  if (!status.value.notification_toggle) {
    return '受限';
  }
  return '正常';
};

onMounted(fetchStatus);
</script>

<style scoped>
.status-section {
  margin: 40px auto 0;
  max-width: 1000px;
}



.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background-color: #fff;
  border-radius: 8px;
  border: 1px solid #e9ecef;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.status-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

.service-name {
  font-weight: 600;
  font-size: 15px;
}

.service-details {
  font-size: 12px;
  color: #6c757d;
  display: block;
  margin-top: 2px;
}

.status-badge {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
  margin-left: 8px;
}

.status-success {
  background-color: #28a745;
}

.status-error {
  background-color: #dc3545;
}

.status-warning {
  background-color: #ffcb21ff;
}

.status-badge.clickable {
  cursor: pointer;
  transition: all 0.2s ease;
}

.status-badge.clickable:hover {
  opacity: 0.8;
  transform: scale(1.05);
}

.status-badge.clickable:active {
  transform: scale(0.95);
}

.status-badge.refreshing {
  position: relative;
  pointer-events: none;
  background-color: transparent !important;
  border: none !important;
  padding: 6px 12px;
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(203, 178, 33, 0.3);
  border-top-color: #ffcb21;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.dark .spinner {
  border: 2px solid rgba(255, 203, 33, 0.3);
  border-top-color: #ffcb21;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.dark .status-item {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.15);
}

.dark .service-name {
  color: #f1f1f1;
}

.dark .service-details {
  color: rgba(255, 255, 255, 0.6);
}

.error-message {
  color: #dc3545;
  text-align: center;
}
</style>