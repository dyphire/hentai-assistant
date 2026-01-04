<template>
  <div class="download-view">
    <h1>提交下载任务</h1>
    <form @submit.prevent="submitDownload">
      <div class="form-group">
        <label for="url">URL:</label>
        <input type="text" id="url" v-model="url" required placeholder="请输入下载链接" />
      </div>
      <div class="form-group">
        <label for="mode">下载模式:</label>
        <div class="custom-select-wrapper">
          <div
            class="custom-select"
            @click="toggleDropdown"
            :class="{ 'custom-select-open': isDropdownOpen }"
          >
            <span class="custom-select-value">{{ getSelectedLabel() }}</span>
            <span class="custom-select-arrow" :class="{ 'custom-select-arrow-open': isDropdownOpen }">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6,9 12,15 18,9"></polyline>
              </svg>
            </span>
          </div>
          <div v-if="isDropdownOpen" class="custom-dropdown" ref="dropdown">
            <div
              v-for="option in modeOptions"
              :key="option.value"
              class="custom-option"
              :class="{ 'custom-option-selected': mode === option.value }"
              @click="selectOption(option.value)"
            >
              {{ option.label }}
            </div>
          </div>
        </div>
      </div>
      <div class="form-group">
        <label for="favcat">添加到收藏夹 (仅 E-Hentai):</label>
        <div class="custom-select-wrapper">
          <div
            class="custom-select"
            @click="toggleFavcatDropdown"
            :class="{ 'custom-select-open': isFavcatDropdownOpen }"
          >
            <span class="custom-select-value">{{ getSelectedFavcatLabel() }}</span>
            <span class="custom-select-arrow" :class="{ 'custom-select-arrow-open': isFavcatDropdownOpen }">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6,9 12,15 18,9"></polyline>
              </svg>
            </span>
          </div>
          <div v-if="isFavcatDropdownOpen" class="custom-dropdown" ref="favcatDropdown">
            <div
              v-for="option in favcatOptions"
              :key="option.value"
              class="custom-option"
              :class="{ 'custom-option-selected': favcat === option.value }"
              @click="selectFavcatOption(option.value)"
            >
              {{ option.label }}
            </div>
          </div>
        </div>
      </div>
      <button type="submit" :disabled="submitting">提交下载</button>
    </form>

    <div v-if="submitting" class="info-message">提交中...</div>
    <div v-if="submitSuccess" class="success-message">
      {{ submitMessage }}
      任务ID: {{ taskId }}。
      <router-link to="/tasks">查看任务列表</router-link>
    </div>
    <div v-if="submitError" class="error-message">提交失败: {{ submitError }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import axios from 'axios';

const url = ref('');
const mode = ref('');
const submitting = ref(false);
const submitSuccess = ref(false);
const submitError = ref<string | null>(null);
const taskId = ref<string | null>(null);
const submitMessage = ref<string>(''); // 新增：用于显示详细的提交信息

// 下载模式下拉菜单
const isDropdownOpen = ref(false);
const dropdown = ref<HTMLElement | null>(null);
const modeOptions = [
  { value: '', label: '自动选择' },
  { value: 'torrent', label: '种子下载' },
  { value: 'archive', label: '归档下载' }
];

// 收藏夹分类下拉菜单
const favcat = ref<string>('-1'); // -1 表示不添加到收藏夹
const isFavcatDropdownOpen = ref(false);
const favcatDropdown = ref<HTMLElement | null>(null);
const favcatOptions = ref([
  { value: '-1', label: '-' }
]);

const API_BASE_URL = '/api'; // 使用相对路径，通过 Vite 代理或 Flask 静态服务处理

const fetchFavcatOptions = async () => {
  try {
    const response = await axios.get(`${API_BASE_URL}/ehentai/favorites/categories`);
    if (response.data && Array.isArray(response.data)) {
      const formattedOptions = response.data.map((fav: { id: string; name: string }) => ({
        value: fav.id,
        label: fav.name
      }));
      // 将获取到的选项追加到“-”之后
      favcatOptions.value = [{ value: '-1', label: '-' }, ...formattedOptions];
    }
  } catch (error) {
    console.error('获取收藏夹列表失败:', error);
    // 即使失败，也提供一个默认的列表
    favcatOptions.value = [
      { value: '-1', label: '-' },
      ...Array.from({ length: 10 }, (_, i) => ({ value: `${i}`, label: `Favorites ${i}` }))
    ];
  }
};

// 从localStorage加载保存的下载模式和收藏夹分类
onMounted(() => {
  fetchFavcatOptions(); // 获取收藏夹列表

  const savedMode = localStorage.getItem('downloadMode');
  if (savedMode) {
    mode.value = savedMode;
  }
  const savedFavcat = localStorage.getItem('downloadFavcat');
  if (savedFavcat) {
    favcat.value = savedFavcat;
  }

  // 点击外部关闭下拉菜单
  const handleClickOutside = (event: Event) => {
    const target = event.target as HTMLElement;
    // 关闭下载模式下拉
    if (dropdown.value && !dropdown.value.contains(target) && !target.closest('.custom-select')) {
      isDropdownOpen.value = false;
    }
    // 关闭收藏夹下拉
    if (favcatDropdown.value && !favcatDropdown.value.contains(target) && !target.closest('.custom-select')) {
      isFavcatDropdownOpen.value = false;
    }
  };

  document.addEventListener('click', handleClickOutside);

  // 清理事件监听器
  return () => {
    document.removeEventListener('click', handleClickOutside);
  };
});

// 监听mode变化并保存到localStorage
watch(mode, (newMode) => {
  if (newMode) {
    localStorage.setItem('downloadMode', newMode);
  } else {
    localStorage.removeItem('downloadMode');
  }
});

watch(favcat, (newFavcat) => {
  if (newFavcat) {
    localStorage.setItem('downloadFavcat', newFavcat);
  } else {
    localStorage.removeItem('downloadFavcat');
  }
});

const submitDownload = async () => {
  submitting.value = true;
  submitSuccess.value = false;
  submitError.value = null;
  taskId.value = null;
  submitMessage.value = '';

  try {
    const params: { url: string; mode: string; fav?: string } = {
      url: url.value,
      mode: mode.value,
    };
    
    // 如果选择了收藏夹分类，则添加 fav 参数
    if (favcat.value !== '-1') {
      params.fav = favcat.value;
    }
    
    const response = await axios.get(`${API_BASE_URL}/download`, { params });
    
    // 根据状态码和响应内容显示不同的消息
    if (response.status === 200) {
      // 任务已存在（已完成或进行中）
      submitSuccess.value = true;
      taskId.value = response.data.task_id;
      
      if (response.data.reason === 'already_completed') {
        submitMessage.value = '该任务已完成，无需重复下载。';
      } else if (response.data.reason === 'in_progress') {
        submitMessage.value = '该任务正在进行中。';
      } else {
        submitMessage.value = '任务已存在。';
      }
    } else if (response.status === 202) {
      // 任务已创建或重试
      submitSuccess.value = true;
      taskId.value = response.data.task_id;
      
      if (response.data.retried) {
        // 自动重试
        submitMessage.value = `检测到之前的任务失败，已自动重试。`;
      } else {
        // 新建任务
        submitMessage.value = '任务提交成功！';
      }
      
      url.value = ''; // 只有新建或重试任务时才清空输入
    }
  } catch (err: any) {
    submitError.value = err.response?.data?.error || '提交下载任务失败。';
    console.error(err);
  } finally {
    submitting.value = false;
  }
};

const toggleDropdown = () => {
  isDropdownOpen.value = !isDropdownOpen.value;
};

const getSelectedLabel = () => {
  const selectedOption = modeOptions.find(option => option.value === mode.value);
  return selectedOption ? selectedOption.label : '自动选择';
};

const selectOption = (value: string) => {
  mode.value = value;
  isDropdownOpen.value = false;
  // 保存到localStorage
  if (value) {
    localStorage.setItem('downloadMode', value);
  } else {
    localStorage.removeItem('downloadMode');
  }
};

const toggleFavcatDropdown = () => {
  isFavcatDropdownOpen.value = !isFavcatDropdownOpen.value;
};

const getSelectedFavcatLabel = () => {
  const selectedOption = favcatOptions.value.find(option => option.value === favcat.value);
  return selectedOption ? selectedOption.label : '-';
};

const selectFavcatOption = (value: string) => {
  favcat.value = value;
  isFavcatDropdownOpen.value = false;
  if (value !== '-1') {
    localStorage.setItem('downloadFavcat', value);
  } else {
    localStorage.removeItem('downloadFavcat');
  }
};
</script>

<style scoped>
.download-view {
  padding: 20px;
  max-width: 600px;
  margin: 0 auto;
  font-family: var(--font-family);
  min-height: calc(100vh - 40px);
}

h1 {
  color: var(--text-color-dark);
  text-align: center;
  margin-bottom: 30px;
  font-weight: 700;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--text-color-dark);
}

.form-group input[type="text"] {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  font-size: 16px;
  box-sizing: border-box;
  background-color: var(--white-color);
  color: var(--text-color-dark);
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
}

.form-group select {
  width: 100%;
  padding: 12px 40px 12px 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 16px;
  box-sizing: border-box;
  background-color: var(--white-color);
  color: var(--text-color-dark);
  transition: all 0.3s ease;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236c757d' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6,9 12,15 18,9'%3e%3c/polyline%3e%3c/svg%3e");
  background-repeat: no-repeat;
  background-position: right 12px center;
  background-size: 16px;
  outline: none;
}

.form-group input[type="text"]:focus {
  border-color: var(--primary-color);
  outline: none;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
}

.form-group select:focus {
  border-color: var(--primary-color);
  outline: none;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23007bff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6,9 12,15 18,9'%3e%3c/polyline%3e%3c/svg%3e");
}

button {
  display: block;
  width: 150px;
  padding: 12px 20px;
  background-color: var(--success-color);
  color: var(--white-color);
  border: none;
  border-radius: var(--border-radius);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 25px;
  margin-left: auto;
  margin-right: auto;
  transition: all 0.3s ease;
  box-shadow: var(--box-shadow);
}

button:hover:not(:disabled) {
  background-color: #218838;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(40, 167, 69, 0.3);
}

button:disabled {
  background-color: var(--secondary-color);
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.info-message {
  background-color: var(--info-color-light);
  color: var(--info-color-dark);
  border: 1px solid var(--info-color);
  padding: 12px;
  border-radius: var(--border-radius);
  margin-top: 20px;
  text-align: center;
}

.success-message {
  background-color: var(--success-color-light);
  color: var(--success-color-dark);
  border: 1px solid var(--success-color);
  padding: 12px;
  border-radius: var(--border-radius);
  margin-top: 20px;
  text-align: center;
}

.error-message {
  background-color: var(--danger-color-light);
  color: var(--danger-color-dark);
  border: 1px solid var(--danger-color);
  padding: 12px;
  border-radius: var(--border-radius);
  margin-top: 20px;
  text-align: center;
}

.success-message a {
  color: var(--success-color);
  text-decoration: underline;
  font-weight: 600;
}

.success-message a:hover {
  color: #1e7e34;
}

/* 深色模式适配 */

.dark h1 {
  color: var(--text-color-light);
}

.dark .form-group label {
  color: var(--text-color-light);
}

.dark .form-group input[type="text"] {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.15);
  color: var(--text-color-light);
}

.dark .form-group select {
  background-color: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  color: var(--text-color-light);
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ffffff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6,9 12,15 18,9'%3e%3c/polyline%3e%3c/svg%3e");
  outline: none;
}

.dark .form-group input[type="text"]:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.3);
}

.dark .form-group select:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.3);
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23007bff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6,9 12,15 18,9'%3e%3c/polyline%3e%3c/svg%3e");
}

/* 下拉选择框选项样式 */
.form-group select option {
  background-color: var(--white-color);
  color: var(--text-color-dark);
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 16px;
  line-height: 1.4;
  margin: 2px 0;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.form-group select option:hover {
  background-color: rgba(0, 123, 255, 0.1);
}

/* 自定义下拉选择框样式 */
.custom-select-wrapper {
  position: relative;
  width: 100%;
}

.custom-select {
  width: 100%;
  padding: 12px 40px 12px 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background-color: var(--white-color);
  color: var(--text-color-dark);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  transition: all 0.3s ease;
  font-size: 16px;
  line-height: 1.4;
  box-sizing: border-box;
  position: relative;
}

.custom-select:hover {
  border-color: rgba(0, 123, 255, 0.5);
}

.custom-select:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
}

.custom-select-value {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.custom-select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  transition: transform 0.3s ease;
  color: #6c757d;
  display: flex;
  align-items: center;
  justify-content: center;
}

.custom-select-arrow-open {
  transform: translateY(-50%) rotate(180deg);
}

.custom-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background-color: var(--white-color);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  max-height: 200px;
  overflow-y: auto;
  margin-top: 4px;
}

.custom-option {
  padding: 12px 16px;
  cursor: pointer;
  transition: background-color 0.2s ease;
  font-size: 16px;
  line-height: 1.4;
  border-radius: 6px;
  margin: 2px 4px;
}

.custom-option:hover {
  background-color: rgba(0, 123, 255, 0.1);
}

.custom-option-selected {
  background-color: rgba(0, 123, 255, 0.15);
  color: var(--primary-color);
  font-weight: 600;
}

/* 深色模式自定义下拉选择框样式 */
.dark .custom-select {
  background-color: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.2);
  color: var(--text-color-light);
}

.dark .custom-select:hover {
  border-color: rgba(0, 123, 255, 0.6);
}

.dark .custom-select:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.3);
}

.dark .custom-select-arrow {
  color: var(--text-color-light);
}

.dark .custom-dropdown {
  background-color: rgba(33, 37, 41, 0.98);
  border-color: rgba(255, 255, 255, 0.25);
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.5);
}

.dark .custom-option {
  color: var(--text-color-light);
}

.dark .custom-option:hover {
  background-color: rgba(0, 123, 255, 0.2);
}

.dark .custom-option-selected {
  background-color: rgba(0, 123, 255, 0.25);
  color: var(--primary-color);
}

.dark .info-message {
  background-color: rgba(23, 162, 184, 0.15);
  border-color: rgba(23, 162, 184, 0.3);
  color: rgba(255, 255, 255, 0.9);
}

.dark .success-message {
  background-color: rgba(40, 167, 69, 0.15);
  border-color: rgba(40, 167, 69, 0.3);
  color: rgba(255, 255, 255, 0.9);
}

.dark .error-message {
  background-color: rgba(220, 53, 69, 0.15);
  border-color: rgba(220, 53, 69, 0.3);
  color: rgba(255, 255, 255, 0.9);
}

.dark .success-message a {
  color: #75b798;
}

.dark .success-message a:hover {
  color: #8ecea9;
}

/* 响应式设计 - 移动端优化 */
@media (max-width: 768px) {
  .download-view {
    padding: 16px;
    max-width: none;
  }

  h1 {
    font-size: 1.8rem;
    margin-bottom: 25px;
  }

  .form-group {
    margin-bottom: 18px;
  }

  .form-group input[type="text"],
  .form-group select {
    padding: 14px 16px;
    font-size: 16px; /* 保持字体大小，避免移动端缩放 */
  }

  button {
    width: 100%;
    max-width: 200px;
    padding: 14px;
    font-size: 16px;
  }
}

/* 超小屏幕优化 */
@media (max-width: 480px) {
  .download-view {
    padding: 12px;
  }

  h1 {
    font-size: 1.5rem;
    margin-bottom: 20px;
  }

  .form-group label {
    font-size: 0.95rem;
  }

  .form-group input[type="text"],
  .form-group select {
    padding: 12px 14px;
  }

  button {
    padding: 12px;
    font-size: 15px;
  }
}

/* 触摸设备优化 */
@media (hover: none) and (pointer: coarse) {
  button:hover:not(:disabled) {
    transform: none;
  }

  button:active:not(:disabled) {
    transform: scale(0.98);
  }
}

/* 减少动画对性能敏感用户的影响 */
@media (prefers-reduced-motion: reduce) {
  button,
  .form-group input[type="text"],
  .form-group select {
    transition: none;
  }
}
</style>
