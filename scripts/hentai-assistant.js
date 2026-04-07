// ==UserScript==
// @name         Hentai Assistant
// @namespace    http://tampermonkey.net/
// @version      2.1
// @description  Add a "Hentai Assistant" button on e-hentai.org, exhentai.org and nhentai.net, with menu
// @author       rosystain
// @match        https://e-hentai.org/*
// @match        https://exhentai.org/*
// @match        https://nhentai.net/*
// @match        https://nhentai.xxx/*
// @match        https://hdoujin.org/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_registerMenuCommand
// @require      https://openuserjs.org/src/libs/sizzle/GM_config.js
// @license      MIT
// ==/UserScript==

(function () {
    'use strict';


    const IS_EX = window.location.host.includes("exhentai");
    const IS_NHENTAI = window.location.host.includes("nhentai");
    const IS_HDOUJIN = window.location.host.includes("hdoujin");

    // 使用 localStorage 存储设置
    function getSetting(key, defaultValue) {
        const value = localStorage.getItem('hentai_assistant_' + key);
        return value !== null ? value : defaultValue;
    }

    function setSetting(key, value) {
        localStorage.setItem('hentai_assistant_' + key, value);
    }

    GM_registerMenuCommand("设置", () => {
        showConfigDialog();
    });

    function showConfigDialog() {
        // 移除现有对话框
        const existing = document.getElementById('ha-config-dialog');
        if (existing) existing.remove();

        const currentUrl = getSetting('server_url', '');
        const currentMode = getSetting('download_mode', 'archive');
        const showProgressPopup = getSetting('show_progress_popup', 'true') === 'true';

        // 检测黑暗模式
        const darkMode = window.matchMedia('(prefers-color-scheme: dark)').matches || IS_EX;

        // 添加全局样式
        const style = document.createElement('style');
        style.textContent = `
            #ha-config-dialog select {
                background: ${darkMode ? '#1a1a1a' : '#fff'} !important;
                color: ${darkMode ? '#eee' : '#000'} !important;
            }
            #ha-config-dialog select option {
                background: ${darkMode ? '#1a1a1a' : '#fff'} !important;
                color: ${darkMode ? '#eee' : '#000'} !important;
            }
            #ha-config-dialog select:focus {
                background: ${darkMode ? '#1a1a1a' : '#fff'} !important;
                color: ${darkMode ? '#eee' : '#000'} !important;
            }
            #ha-config-dialog select option:hover,
            #ha-config-dialog select option:focus,
            #ha-config-dialog select option:active {
                background: ${darkMode ? '#333' : '#f0f0f0'} !important;
                color: ${darkMode ? '#eee' : '#000'} !important;
            }
        `;
        document.head.appendChild(style);

        const dialog = document.createElement('div');
        dialog.id = 'ha-config-dialog';
        dialog.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: ${darkMode ? '#2b2b2b' : '#fff'};
            color: ${darkMode ? '#eee' : '#000'};
            border: 2px solid ${darkMode ? '#555' : '#ccc'};
            border-radius: 10px;
            padding: 20px;
            z-index: 10000;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
            min-width: 300px;
            font-family: Arial, sans-serif;
        `;

        dialog.innerHTML = `
            <h3 style="margin-top: 0; color: ${darkMode ? '#eee' : '#333'};">Hentai Assistant 设置</h3>
            <div style="margin-bottom: 15px;">
                <label style="display: block; margin-bottom: 5px;">服务器地址:</label>
                <input type="text" id="ha-server-url" value="${currentUrl}" placeholder="http://127.0.0.1:5001" style="width: 100%; padding: 8px; border: 1px solid ${darkMode ? '#666' : '#ccc'}; border-radius: 3px; background: ${darkMode ? '#1a1a1a' : '#fff'}; color: ${darkMode ? '#eee' : '#000'};">
            </div>
            <div style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 5px;">快捷按钮下载模式:</label>
                <select id="ha-download-mode" style="width: 100%; padding: 8px; border: 1px solid ${darkMode ? '#666' : '#ccc'}; border-radius: 3px; background: ${darkMode ? '#1a1a1a' : '#fff'}; color: ${darkMode ? '#eee' : '#000'};">
                    <option value="archive" ${currentMode === 'archive' ? 'selected' : ''} style="background: ${darkMode ? '#1a1a1a' : '#fff'}; color: ${darkMode ? '#eee' : '#000'};">Archive (归档)</option>
                    <option value="torrent" ${currentMode === 'torrent' ? 'selected' : ''} style="background: ${darkMode ? '#1a1a1a' : '#fff'}; color: ${darkMode ? '#eee' : '#000'};">Torrent (种子)</option>
                </select>
            </div>
            <div style="margin-bottom: 20px;">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" id="ha-show-progress-popup" ${showProgressPopup ? 'checked' : ''} style="width: 16px; height: 16px; margin: 0;">
                    <span>显示进度弹窗</span>
                </label>
                <div style="margin-top: 5px; font-size: 12px; color: ${darkMode ? '#ccc' : '#666'};">控制是否显示下载进度弹窗</div>
            </div>
            <div style="text-align: right;">
                <button id="ha-save-btn" style="padding: 8px 16px; margin-right: 10px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer;">保存</button>
                <button id="ha-cancel-btn" style="padding: 8px 16px; background: ${darkMode ? '#555' : '#6c757d'}; color: white; border: none; border-radius: 3px; cursor: pointer;">取消</button>
            </div>
        `;

        document.body.appendChild(dialog);

        // 绑定事件
        document.getElementById('ha-save-btn').onclick = () => {
            const url = document.getElementById('ha-server-url').value.trim();
            const mode = document.getElementById('ha-download-mode').value;
            const showProgress = document.getElementById('ha-show-progress-popup').checked;

            if (url) {
                setSetting('server_url', url.replace(/\/$/, ''));
                setSetting('download_mode', mode);
                setSetting('show_progress_popup', showProgress.toString());
                showToast('设置已保存', 'success');
                style.remove();
                dialog.remove();
            } else {
                showToast('请输入服务器地址', 'error');
            }
        };

        document.getElementById('ha-cancel-btn').onclick = () => {
            style.remove();
            dialog.remove();
        };

        // 点击对话框外部关闭
        dialog.onclick = (e) => {
            if (e.target === dialog) {
                style.remove();
                dialog.remove();
            }
        };
    }

    const SERVER_URL = getSetting('server_url', '');
    const DOWNLOAD_MODE = getSetting('download_mode', 'archive');



    // ========== Toast 模块 ==========
    function createToastContainer() {
        let container = document.getElementById('ha-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'ha-toast-container';
            container.style.position = 'fixed';
            container.style.top = '20px';
            container.style.right = '20px';
            container.style.display = 'flex';
            container.style.flexDirection = 'column';
            container.style.gap = '10px';
            container.style.zIndex = 10000;
            document.body.appendChild(container);
        }
        return container;
    }

        // 发送下载任务函数
        function sendDownload(url, mode) {
            if (!SERVER_URL) {
                showToast('请先设置服务器地址', 'error');
                return;
            }

            let apiUrl = `${SERVER_URL}/api/download?url=${encodeURIComponent(url)}&mode=${mode}`;

            if (IS_NHENTAI) {
                // 为nhentai添加特殊处理参数
                apiUrl += '&source=nhentai';

                // 如果是详情页，尝试获取画廊ID
                if (isNHentaiDetailPage()) {
                    const galleryInfo = getNHentaiGalleryInfo();
                    if (galleryInfo) {
                        apiUrl += `&gallery_id=${galleryInfo.id}&title=${encodeURIComponent(galleryInfo.title)}`;
                    }
                }
            } else if (IS_HDOUJIN) {
                // 为hdoujin添加特殊处理参数
                apiUrl += '&source=hdoujin';

                // 如果是详情页，尝试获取画廊ID
                if (isHDoujinDetailPage()) {
                    const galleryInfo = getHDoujinGalleryInfo();
                    if (galleryInfo) {
                        apiUrl += `&gallery_id=${galleryInfo.id}&title=${encodeURIComponent(galleryInfo.title)}`;
                    }
                }
            }

            GM_xmlhttpRequest({
                method: 'GET',
                url: apiUrl,
                onload: function (response) {
                    try {
                        const data = JSON.parse(response.responseText);
                        if (data && data.task_id) {
                            const taskId = data.task_id;
                            const siteName = IS_NHENTAI ? 'NHentai' : (IS_HDOUJIN ? 'HDoujin' : (IS_EX ? 'ExHentai' : 'E-Hentai'));
                            showToast(`已推送 ${siteName} 下载任务（mode=${mode}），task_id=${taskId}`, 'success');

                            // 添加到活跃任务并开始轮询进度
                            activeTasks[taskId] = {
                                status: '进行中',
                                progress: 0,
                                downloaded: 0,
                                total_size: 0,
                                speed: 0,
                                filename: null,
                                lastUpdate: Date.now()
                            };

                            // 保存到localStorage
                            saveTasksToStorage();

                            updateProgressPanel();
                            pollAllTasks(); // 使用批量查询
                        } else {
                            showToast('推送失败：返回数据异常', 'error');
                        }
                    } catch (err) {
                        showToast('推送失败：返回数据非 JSON', 'error');
                    }
                },
                onerror: function (err) {
                    showToast('推送失败：请求出错，服务器连接失败', 'error');
                }
            });
        }

    function showToast(message, type = 'info', duration = 3000) {
        const container = createToastContainer();
        const toast = document.createElement('div');

        // 判断是否暗色模式
        const darkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const bg = {
            info: darkMode ? '#333' : '#fff',
            success: darkMode ? '#2e7d32' : '#d4edda',
            error: darkMode ? '#c62828' : '#f8d7da'
        };
        const color = {
            info: darkMode ? '#eee' : '#000',
            success: darkMode ? '#c8e6c9' : '#155724',
            error: darkMode ? '#ffcdd2' : '#721c24'
        };

        toast.textContent = message;
        toast.style.padding = '10px 16px';
        toast.style.borderRadius = '6px';
        toast.style.boxShadow = '0 2px 6px rgba(0,0,0,0.2)';
        toast.style.background = bg[type];
        toast.style.color = color[type];
        toast.style.fontSize = '14px';
        toast.style.maxWidth = '300px';
        toast.style.wordBreak = 'break-word';
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s ease';

        container.appendChild(toast);

        // 渐显
        requestAnimationFrame(() => {
            toast.style.opacity = '1';
        });

        // 自动消失
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    // 初始化 Toast 容器
    createToastContainer();

    // ========== 全局变量 ==========
    let activeTasks = loadTasksFromStorage(); // 从localStorage恢复任务状态
    let progressPanel = null; // 进度面板变量

    // 清理过期任务
    clearExpiredTasks();

    // 预创建进度面板
    createProgressPanel();

    // 如果有活跃任务，立即更新显示并开始轮询
    if (Object.keys(activeTasks).length > 0) {
        updateProgressPanel();
        pollAllTasks();
    }

    // 定期检查页面变化，确保进度面板在页面跳转后能正确恢复
    let lastUrl = window.location.href;
    setInterval(() => {
        if (window.location.href !== lastUrl) {
            lastUrl = window.location.href;
            progressPanel = null;
            if (Object.keys(activeTasks).length > 0) {
                setTimeout(updateProgressPanel, 200);
            }

            // 页面变化时重新检测并注入按钮
            if (IS_NHENTAI) {
                if (isNHentaiDetailPage()) {
                    setTimeout(() => {
                        addNHentaiDetailButton();
                        observeNHentaiInfoContainer();
                    }, 1000);
                } else if (isNHentaiListPage()) {
                    setTimeout(addNHentaiListButtons, 1000);
                }
            } else if (IS_HDOUJIN) {
                if (isHDoujinDetailPage()) {
                    setTimeout(() => {
                        addHDoujinDetailButton();
                        observeHDoujinActionsContainer();
                    }, 1000);
                } else if (isHDoujinListPage()) {
                    setTimeout(addHDoujinListButtons, 1000);
                }
            }
        }
    }, 1000);

    // 定期清理过期任务（每5分钟清理一次）
    setInterval(() => {
        clearExpiredTasks();
    }, 5 * 60 * 1000);

    // ========== 进度显示模块 ==========
    // progressPanel 已经在上面声明，这里不再重复声明

    // 持久化存储相关函数
    const STORAGE_KEY = 'hentai_assistant_active_tasks';
    const STORAGE_EXPIRY = 24 * 60 * 60 * 1000; // 24小时过期

    function saveTasksToStorage() {
        const data = {
            tasks: activeTasks,
            timestamp: Date.now(),
            version: '1.0'
        };
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (e) {
            // 保存失败，静默处理
        }
    }

    function loadTasksFromStorage() {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (!stored) return {};

            const data = JSON.parse(stored);
            const now = Date.now();

            // 检查数据是否过期
            if (now - data.timestamp > STORAGE_EXPIRY) {
                localStorage.removeItem(STORAGE_KEY);
                return {};
            }

            // 验证数据结构
            if (!data.tasks || typeof data.tasks !== 'object') {
                return {};
            }

            return data.tasks;
        } catch (e) {
            return {};
        }
    }

    function clearExpiredTasks() {
        // 清理已完成的或过期的任务
        const now = Date.now();
        let hasChanges = false;

        for (const [taskId, task] of Object.entries(activeTasks)) {
            // 如果任务已完成或失败，且超过5分钟，自动清理
            if ((task.status === '完成' || task.status === '错误' || task.status === '取消') &&
                now - (task.lastUpdate || 0) > 5 * 60 * 1000) {
                delete activeTasks[taskId];
                hasChanges = true;
            }
        }

        if (hasChanges) {
            saveTasksToStorage();
        }
    }

    function createProgressPanel() {
        // 检查是否已经存在，如果存在则返回
        let existingPanel = document.getElementById('ha-progress-panel');
        if (existingPanel) {
            progressPanel = existingPanel;
            return progressPanel;
        }

        const darkMode = window.matchMedia('(prefers-color-scheme: dark)').matches || IS_EX;
        const colors = {
            bg: darkMode ? '#2b2b2b' : '#fff',
            fg: darkMode ? '#eee' : '#000',
            border: darkMode ? '#555' : '#ccc'
        };

        progressPanel = document.createElement('div');
        progressPanel.id = 'ha-progress-panel';
        progressPanel.style.cssText = `
            position: fixed; bottom: 20px; right: 20px;
            background: ${colors.bg}; color: ${colors.fg};
            border: 2px solid ${colors.border}; border-radius: 10px;
            padding: 15px; z-index: 10002;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
            min-width: 320px; max-width: 450px; max-height: 400px;
            font-family: Arial, sans-serif; display: none;
            pointer-events: auto; overflow: hidden;
        `;

        const header = document.createElement('div');
        header.textContent = 'Hentai Assistant 下载进度';
        header.style.cssText = `
            font-weight: bold; margin-bottom: 10px; text-align: center;
            border-bottom: 1px solid ${colors.border}; padding-bottom: 5px;
        `;

        const taskList = document.createElement('div');
        taskList.id = 'ha-task-list';
        taskList.style.cssText = 'max-height: 300px; overflow-y: auto; overflow-x: hidden;';

        progressPanel.appendChild(header);
        progressPanel.appendChild(taskList);

        // 确保body存在后再添加
        if (document.body) {
            document.body.appendChild(progressPanel);
        } else {
            // 如果body还不存在，等待DOM加载完成
            document.addEventListener('DOMContentLoaded', () => {
                document.body.appendChild(progressPanel);
            });
        }

        return progressPanel;
    }

    function updateProgressPanel() {
        const panel = createProgressPanel();
        const taskList = document.getElementById('ha-task-list');

        // 检查是否应该显示进度弹窗
        const showProgressPopup = getSetting('show_progress_popup', 'true') === 'true';
        if (!showProgressPopup || Object.keys(activeTasks).length === 0) {
            panel.style.display = 'none';
            return;
        }

        // 检测黑暗模式
        const darkMode = window.matchMedia('(prefers-color-scheme: dark)').matches || IS_EX;

        panel.style.display = 'block';
        panel.style.zIndex = '10002';

        // 根据任务数量动态调整弹窗大小
        const taskCount = Object.keys(activeTasks).length;
        const maxHeight = Math.min(400, Math.max(200, taskCount * 80 + 60)); // 动态高度
        panel.style.maxHeight = maxHeight + 'px';

        taskList.innerHTML = '';
        taskList.style.maxHeight = (maxHeight - 60) + 'px';

        for (const [taskId, task] of Object.entries(activeTasks)) {
            const taskDiv = document.createElement('div');
            taskDiv.style.cssText = `
                margin-bottom: 8px; padding: 6px;
                background: ${darkMode ? '#1a1a1a' : '#f8f9fa'};
                border-radius: 4px; border: 1px solid ${darkMode ? '#444' : '#ddd'};
                position: relative;
            `;

            const closeBtn = document.createElement('div');
            closeBtn.textContent = '×';
            closeBtn.style.cssText = `
                position: absolute; top: 2px; right: 6px; cursor: pointer;
                color: ${darkMode ? '#ccc' : '#666'}; font-size: 14px;
                line-height: 1; width: 16px; height: 16px; text-align: center;
            `;
            closeBtn.onclick = (e) => {
                e.stopPropagation();
                delete activeTasks[taskId];
                saveTasksToStorage(); // 保存删除操作
                updateProgressPanel();
            };
            taskDiv.appendChild(closeBtn);

            const title = document.createElement('div');
            title.textContent = task.filename || `任务 ${taskId}`;
            title.style.cssText = `
                font-size: 11px; margin-bottom: 4px;
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
                padding-right: 20px;
            `;

            const status = document.createElement('div');
            status.textContent = `状态: ${task.status}`;
            status.style.cssText = `font-size: 10px; margin-bottom: 4px; color: ${getStatusColor(task.status)};`;

            const progressBar = document.createElement('div');
            progressBar.style.cssText = `
                width: 100%; height: 6px; background: ${darkMode ? '#333' : '#e9ecef'};
                border-radius: 3px; overflow: hidden; margin-bottom: 4px;
            `;

            const progressFill = document.createElement('div');
            progressFill.style.cssText = `
                height: 100%; background: ${getProgressColor(task.status)};
                width: ${task.progress || 0}%; transition: width 0.3s ease;
            `;
            progressBar.appendChild(progressFill);

            const details = document.createElement('div');
            const downloaded = formatBytes(task.downloaded || 0);
            const total = formatBytes(task.total_size || 0);
            const speed = formatBytes(task.speed || 0) + '/s';
            details.textContent = `${task.progress || 0}% (${downloaded}/${total}) ${speed}`;
            details.style.cssText = `font-size: 9px; color: ${darkMode ? '#ccc' : '#666'};`;

            taskDiv.appendChild(title);
            taskDiv.appendChild(status);
            taskDiv.appendChild(progressBar);
            taskDiv.appendChild(details);
            taskList.appendChild(taskDiv);
        }

        let globalCloseBtn = document.getElementById('ha-global-close');
        if (!globalCloseBtn) {
            globalCloseBtn = document.createElement('div');
            globalCloseBtn.id = 'ha-global-close';
            globalCloseBtn.textContent = '清空全部';
            globalCloseBtn.style.cssText = `
                position: absolute; top: 8px; right: 15px; cursor: pointer;
                color: ${darkMode ? '#ccc' : '#666'}; font-size: 10px; text-decoration: underline;
            `;
            globalCloseBtn.onclick = () => {
                activeTasks = {};
                saveTasksToStorage(); // 保存清空操作
                updateProgressPanel();
            };
            panel.appendChild(globalCloseBtn);
        }
    }

    function getStatusColor(status) {
        const colors = {
            '进行中': '#007bff',
            '完成': '#28a745',
            '错误': '#dc3545',
            '取消': '#ffc107'
        };
        return colors[status] || '#6c757d';
    }

    const getProgressColor = getStatusColor;

    function formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }


    function pollAllTasks() {
        if (!SERVER_URL) return;

        const activeTaskIds = Object.keys(activeTasks);
        if (activeTaskIds.length === 0) return;

        // 如果只有一个任务，使用单个查询
        if (activeTaskIds.length === 1) {
            pollTaskProgress(activeTaskIds[0]);
            return;
        }

        // 批量查询所有活跃任务
        const apiUrl = `${SERVER_URL}/api/tasks?status=进行中&page=1&page_size=100`;

        GM_xmlhttpRequest({
            method: 'GET',
            url: apiUrl,
            onload: function (response) {
                try {
                    const data = JSON.parse(response.responseText);
                    if (data.tasks) {
                        let hasActiveTasks = false;

                        data.tasks.forEach(task => {
                            if (activeTasks[task.id]) {
                                activeTasks[task.id] = {
                                    status: task.status,
                                    progress: task.progress || 0,
                                    downloaded: task.downloaded || 0,
                                    total_size: task.total_size || 0,
                                    speed: task.speed || 0,
                                    filename: task.filename,
                                    lastUpdate: Date.now()
                                };

                                if (task.status === '进行中') {
                                    hasActiveTasks = true;
                                } else {
                                    // 任务完成或失败，显示最终状态
                                    showToast(`任务 ${task.filename || task.id} ${task.status}`, task.status === '完成' ? 'success' : 'error');

                                    // 延迟移除任务
                                    setTimeout(() => {
                                        delete activeTasks[task.id];
                                        saveTasksToStorage(); // 保存删除操作
                                        updateProgressPanel();
                                    }, 5000);
                                }
                            }
                        });

                        // 保存状态更新
                        saveTasksToStorage();

                        updateProgressPanel();

                        // 如果还有活跃任务，继续轮询
                        if (hasActiveTasks) {
                            setTimeout(() => pollAllTasks(), 2000);
                        }
                    }
                } catch (err) {
                    // 批量查询失败，回退到单个查询
                    activeTaskIds.forEach(taskId => {
                        if (activeTasks[taskId] && activeTasks[taskId].status === '进行中') {
                            pollTaskProgress(taskId);
                        }
                    });
                }
            },
            onerror: function (err) {
                // 批量查询失败，回退到单个查询
                activeTaskIds.forEach(taskId => {
                    if (activeTasks[taskId] && activeTasks[taskId].status === '进行中') {
                        pollTaskProgress(taskId);
                    }
                });
            }
        });
    }

    function pollTaskProgress(taskId) {
        if (!SERVER_URL) return;

        const apiUrl = `${SERVER_URL}/api/task/${taskId}`;

        GM_xmlhttpRequest({
            method: 'GET',
            url: apiUrl,
            onload: function (response) {
                try {
                    const task = JSON.parse(response.responseText);
                    if (task && !task.error) {
                        activeTasks[taskId] = {
                            status: task.status,
                            progress: task.progress || 0,
                            downloaded: task.downloaded || 0,
                            total_size: task.total_size || 0,
                            speed: task.speed || 0,
                            filename: task.filename,
                            lastUpdate: Date.now()
                        };

                        // 保存状态更新
                        saveTasksToStorage();

                        updateProgressPanel();

                        // 如果任务仍在进行中，继续轮询
                        if (task.status === '进行中') {
                            setTimeout(() => pollTaskProgress(taskId), 2000); // 每2秒轮询一次
                        } else {
                            // 任务完成或失败，显示最终状态
                            showToast(`任务 ${task.filename || taskId} ${task.status}`, task.status === '完成' ? 'success' : 'error');

                            // 延迟移除任务
                            setTimeout(() => {
                                delete activeTasks[taskId];
                                saveTasksToStorage(); // 保存删除操作
                                updateProgressPanel();
                            }, 5000);
                        }
                    } else {
                        // 任务不存在或查询失败
                    }
                } catch (err) {
                    // 解析失败
                }
            },
            onerror: function (err) {
                // 获取失败
            }
        });
    }

    // 添加样式
    const style = document.createElement('style');
    style.textContent = `
    .ha-download-btn {
        width: 15px;
        height: 15px;
        background: radial-gradient(#ffc36b,#c56a00);
        border-radius: 15px;
        border: 1px #666 solid;
        box-sizing: border-box;
        color: #ebeae9;
        text-align: center;
        line-height: 15px;
        cursor: pointer;
        user-select: none;
        margin-left: 4px;
        vertical-align: -1.5px;
    }
    .ha-download-btn:hover {
        background: radial-gradient(#bf893b,#985200);
    }
    .gldown {
        width: 35px !important;
        display: flex;
        flex-direction: row;
        justify-content: space-between;
    }
    .gl3e > div:nth-child(6) {
        left: 45px;
    }

    /* NHentai 样式 */
    .nhentai-ha-container {
        margin-top: 5px;
        padding: 0;
        border: none;
        border-radius: 0;
        background: transparent;
        text-align: left;
        display: inline-block;
        vertical-align: top;
    }

    .nhentai-ha-container.dark {
        background: transparent;
        color: #eee;
    }

    .nhentai-ha-btn {
        padding: 6px 12px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 12px;
        font-weight: normal;
        transition: all 0.2s ease;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        display: inline-block;
        line-height: 26px;
        vertical-align: top;
    }

    .nhentai-ha-btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }

    .nhentai-ha-btn:active {
        transform: translateY(0);
    }

    /* NHentai 列表页按钮样式 */
    .nhentai-list-btn {
        position: absolute;
        top: 8px;
        right: 8px;
        width: 32px;
        height: 32px;
        background: rgba(128, 128, 128, 0.8);
        border-radius: 8px;
        color: white;
        text-align: center;
        line-height: 28px;
        cursor: pointer;
        font-size: 16px;
        z-index: 10;
        transition: all 0.2s ease;
        border: 2px solid rgba(255, 255, 255, 0.3);
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .nhentai-list-btn:hover {
        background: rgba(128, 128, 128, 1);
        transform: scale(1.05);
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }

    /* HDoujin 样式 */
    .hdoujin-ha-container {
        margin-top: -15px;
        padding: 0;
        border: none;
        border-radius: 0;
        background: transparent;
        text-align: left;
        display: inline-block;
        vertical-align: top;
    }

    .hdoujin-ha-container.dark {
        background: transparent;
        color: #eee;
    }

    .hdoujin-ha-btn {
        padding: 6px 12px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 12px;
        font-weight: normal;
        transition: all 0.2s ease;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        display: inline-block;
        line-height: 26px;
        vertical-align: top;
    }

    .hdoujin-ha-btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }

    .hdoujin-ha-btn:active {
        transform: translateY(0);
    }

    /* HDoujin 列表页按钮样式 */
    .hdoujin-list-btn {
        position: absolute;
        top: 8px;
        right: 8px;
        width: 32px;
        height: 32px;
        background: rgba(128, 128, 128, 0.8);
        border-radius: 8px;
        color: white;
        text-align: center;
        line-height: 28px;
        cursor: pointer;
        font-size: 16px;
        z-index: 10;
        transition: all 0.2s ease;
        border: 2px solid rgba(255, 255, 255, 0.3);
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .hdoujin-list-btn:hover {
        background: rgba(128, 128, 128, 1);
        transform: scale(1.05);
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }
    `;
    document.head.appendChild(style);


    // ========== NHentai 功能 ==========
    // 获取nhentai画廊信息
    function getNHentaiGalleryInfo() {
        const urlMatch = window.location.pathname.match(/^\/g\/(\d+)/);
        if (!urlMatch) return null;

        const galleryId = urlMatch[1];

        // 尝试从页面获取信息
        const titleElement = document.querySelector('#info h1, #info h2');
        const title = titleElement ? titleElement.textContent.trim() : `NHentai Gallery ${galleryId}`;

        return {
            id: galleryId,
            title: title,
            url: window.location.href
        };
    }

    // ========== HDoujin 功能 ==========
    // 获取hdoujin画廊信息
    function getHDoujinGalleryInfo() {
        const urlMatch = window.location.pathname.match(/^\/g\/(\d+)\/([a-f0-9]+)/);
        if (!urlMatch) return null;

        const galleryId = urlMatch[1];
        const hash = urlMatch[2];

        // 尝试从页面获取信息
        const titleElement = document.querySelector('h1');
        const title = titleElement ? titleElement.textContent.trim() : `HDoujin Gallery ${galleryId}`;

        return {
            id: galleryId,
            hash: hash,
            title: title,
            url: window.location.href
        };
    }

    // 读取并存储HDoujin认证信息
    function storeHDoujinAuthTokens() {
        try {
            let hasChanges = false;

            // 读取localStorage中的clearance信息
            const clearance = localStorage.getItem('clearance');
            const currentClearance = getSetting('hdoujin_clearance', '');
            if (clearance && clearance !== currentClearance) {
                // 存储clearance token
                setSetting('hdoujin_clearance', clearance);
                hasChanges = true;
            }

            // 读取localStorage中的token信息
            const tokenData = localStorage.getItem('token');
            if (tokenData) {
                try {
                    const token = JSON.parse(tokenData);
                    if (token && token.refresh) {
                        const currentRefresh = getSetting('hdoujin_refresh_token', '');
                        if (token.refresh !== currentRefresh) {
                            // 存储refresh token
                            setSetting('hdoujin_refresh_token', token.refresh);
                            hasChanges = true;
                        }
                    }
                } catch (e) {
                    // 解析失败，静默处理
                }
            }

            // 获取当前的 User-Agent
            const userAgent = navigator.userAgent;
            const currentUserAgent = getSetting('hdoujin_user_agent', '');
            if (userAgent && userAgent !== currentUserAgent) {
                setSetting('hdoujin_user_agent', userAgent);
                hasChanges = true;
            }

            // 如果有变化，通知后端更新
            if (hasChanges && SERVER_URL) {
                GM_xmlhttpRequest({
                    method: 'POST',
                    url: `${SERVER_URL}/api/hdoujin/refresh`,
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    data: JSON.stringify({
                        clearance: clearance,
                        refresh_token: tokenData ? JSON.parse(tokenData).refresh : null,
                        user_agent: userAgent
                    }),
                    onload: function (response) {
                        try {
                            const data = JSON.parse(response.responseText);
                            if (data && data.success) {
                                console.log('成功更新 HDoujin tokens');
                            }
                        } catch (e) {
                            // 静默处理
                        }
                    },
                    onerror: function (err) {
                        // 静默处理
                    }
                });
            }
        } catch (e) {
            // 读取失败，静默处理
        }
    }

    // 读取并存储HDoujin认证信息
    if (IS_HDOUJIN) {
        storeHDoujinAuthTokens();
        // 定期更新认证令牌（每30秒检查一次）
        setInterval(storeHDoujinAuthTokens, 30000);
    }

    // 检查是否为nhentai详情页
    function isNHentaiDetailPage() {
        return IS_NHENTAI && /^\/g\/\d+/.test(window.location.pathname);
    }

    // 检查是否为nhentai列表页
    function isNHentaiListPage() {
        return IS_NHENTAI && (window.location.pathname === '/' 
            || window.location.pathname.startsWith('/search')
            || window.location.pathname.startsWith('/tag')
            || window.location.pathname.startsWith('/favorites'));
    }

    // 检查是否为hdoujin详情页
    function isHDoujinDetailPage() {
        return IS_HDOUJIN && /^\/g\/\d+\/[a-f0-9]+/.test(window.location.pathname);
    }

    // 检查是否为hdoujin列表页
    function isHDoujinListPage() {
        return IS_HDOUJIN && (window.location.pathname === '/' 
            || window.location.pathname.startsWith('/popular')
            || window.location.pathname.startsWith('/browse')
            || window.location.pathname.startsWith('/favorites'));
    }

    // ========== NHentai 按钮注入函数 ==========
    function addNHentaiDetailButton(retries = 0) {
        const infoElement = document.querySelector('#info');
        const actionsElement = document.querySelector('#info .buttons.btn-group, .buttons.btn-group');

        if (!infoElement) {
            if (retries < 5) {
                setTimeout(() => addNHentaiDetailButton(retries + 1), 600);
            }
            return;
        }

        // 已经添加过按钮则不重复添加
        if ((actionsElement && actionsElement.querySelector('.nhentai-ha-btn')) || document.querySelector('.nhentai-ha-container')) {
            return;
        }

        const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'nhentai-ha-btn';
        downloadBtn.textContent = '📥 Hentai Assistant 下载';

        if (actionsElement) {
            downloadBtn.classList.add('btn', 'btn-secondary');
            downloadBtn.style.marginLeft = '0';
        } else {
            downloadBtn.style.marginLeft = '8px';
        }

        downloadBtn.onclick = () => {
            const currentUrl = window.location.href;
            const galleryInfo = getNHentaiGalleryInfo();
            if (galleryInfo) {
                showToast(`正在推送 NHentai 画廊: ${galleryInfo.title}`, 'info');
            }
            sendDownload(currentUrl, DOWNLOAD_MODE);
        };

        if (actionsElement) {
            actionsElement.appendChild(downloadBtn);
        } else {
            const buttonContainer = document.createElement('div');
            buttonContainer.className = `nhentai-ha-container${isDark ? ' dark' : ''}`;
            buttonContainer.appendChild(downloadBtn);
            infoElement.appendChild(buttonContainer);
        }

        // 同时检查页面下方的画廊卡片并注入按钮
        addNHentaiDetailGalleryButtons();
    }

    // 监听 NHentai 详情页面 #info 变化，确保按钮不会被页面后续渲染移除
    let nhentaiInfoObserver = null;
    function observeNHentaiInfoContainer() {
        const rootElement = document.querySelector('body');
        if (!rootElement) return;

        if (nhentaiInfoObserver) {
            nhentaiInfoObserver.disconnect();
        }

        nhentaiInfoObserver = new MutationObserver((mutations) => {
            if (!isNHentaiDetailPage()) return;
            addNHentaiDetailButton();
        });

        nhentaiInfoObserver.observe(rootElement, { childList: true, subtree: true });
    }

    // ========== HDoujin 按钮注入函数 ==========
    function addHDoujinDetailButton() {
        const actionsElement = document.querySelector('div.actions');
        if (!actionsElement) return;

        // 如果已经在 actions里有按钮，直接返回
        if (actionsElement.querySelector('.hdoujin-ha-btn')) return;

        // 检测黑暗模式
        const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

        // 创建下载按钮
        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'hdoujin-ha-btn';
        downloadBtn.textContent = '📥 Hentai Assistant 下载';
        downloadBtn.style.marginLeft = '8px';

        // 与原生按钮样式一致
        if (actionsElement) {
            downloadBtn.classList.add('btn', 'btn-secondary');
            downloadBtn.style.marginLeft = '0';
        } else {
            downloadBtn.style.marginLeft = '8px';
        }

        downloadBtn.onclick = () => {
            const currentUrl = window.location.href;
            const galleryInfo = getHDoujinGalleryInfo();
            if (galleryInfo) {
                showToast(`正在推送 HDoujin 画廊: ${galleryInfo.title}`, 'info');
            }
            sendDownload(currentUrl, 'archive');
        };

        actionsElement.appendChild(downloadBtn);

        // 同时检查页面下方的画廊卡片并注入按钮
        addHDoujinDetailGalleryButtons();
    }

    // 监听 HDoujin 详情页面 actions 区变化，确保按钮不会被页面后续渲染移除
    let hdoujinActionsObserver = null;
    function observeHDoujinActionsContainer() {
        const rootElement = document.querySelector('body');
        if (!rootElement) return;

        if (hdoujinActionsObserver) {
            hdoujinActionsObserver.disconnect();
        }

        hdoujinActionsObserver = new MutationObserver(() => {
            if (!isHDoujinDetailPage()) return;
            addHDoujinDetailButton();
        });

        hdoujinActionsObserver.observe(rootElement, { childList: true, subtree: true });
    }

    // 为详情页下方的画廊卡片注入按钮
    function addNHentaiDetailGalleryButtons() {
        const galleryLinks = document.querySelectorAll('.gallery a.cover');
        const processedContainers = new Set();

        galleryLinks.forEach(link => {
            // 确保是画廊链接（包含/g/路径）
            if (!link.href || !link.href.includes('/g/')) return;

            const container = link.closest('.gallery') || link.parentElement;
            if (!container || processedContainers.has(container)) return;

            // 检查是否已经注入了按钮
            if (container.querySelector('.nhentai-list-btn')) return;

            const downloadBtn = document.createElement('div');
            downloadBtn.textContent = '📥';
            downloadBtn.title = '[Hentai Assistant] 推送下载';
            downloadBtn.className = 'nhentai-list-btn';
            downloadBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                showToast('正在推送相关 NHentai 画廊下载任务...', 'info');
                sendDownload(link.href, DOWNLOAD_MODE);
            };

            // 设置相对定位
            if (container.style.position !== 'relative') {
                container.style.position = 'relative';
            }

            container.appendChild(downloadBtn);
            processedContainers.add(container);
        });
    }

    function addNHentaiListButtons() {
        // 可以扩展选择器以覆盖更多类型的画廊卡片
        const gallerySelectors = [
            '.gallery a.cover',           // 标准画廊链接
        ];

        const processedContainers = new Set();

        gallerySelectors.forEach(selector => {
            const galleryLinks = document.querySelectorAll(selector);
            galleryLinks.forEach(link => {
                // 确保是画廊链接（包含/g/路径）
                if (!link.href || !link.href.includes('/g/')) return;

                const container = link.closest('.gallery') || link.parentElement;
                if (!container || processedContainers.has(container)) return;

                // 检查是否已经注入了按钮
                if (container.querySelector('.nhentai-list-btn')) return;

                const downloadBtn = document.createElement('div');
                downloadBtn.textContent = '📥';
                downloadBtn.title = '[Hentai Assistant] 推送下载';
                downloadBtn.className = 'nhentai-list-btn';
                downloadBtn.onclick = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    showToast('正在推送 NHentai 画廊下载任务...', 'info');
                    sendDownload(link.href, DOWNLOAD_MODE);
                };

                // 设置相对定位
                if (container.style.position !== 'relative') {
                    container.style.position = 'relative';
                }

                container.appendChild(downloadBtn);
                processedContainers.add(container);
            });
        });

        // 定期检查新加载的内容（处理分页和动态加载）
        setTimeout(addNHentaiListButtons, 2000);
    }

    function addHDoujinListButtons() {
        // 只有在列表页时才注入按钮
        if (!isHDoujinListPage()) return;

        // HDoujin的画廊卡片选择器
        const gallerySelectors = [
            'a[href*="/g/"]',  // 包含画廊链接的元素
        ];

        const processedContainers = new Set();

        gallerySelectors.forEach(selector => {
            const galleryLinks = document.querySelectorAll(selector);
            galleryLinks.forEach(link => {
                // 确保是画廊链接（包含/g/路径且有hash）
                if (!link.href || !link.href.match(/\/g\/\d+\/[a-f0-9]+/)) return;

                const container = link.closest('article') || link.parentElement;
                if (!container || processedContainers.has(container)) return;

                // 检查是否已经注入了按钮
                if (container.querySelector('.hdoujin-list-btn')) return;

                const downloadBtn = document.createElement('div');
                downloadBtn.textContent = '📥';
                downloadBtn.title = '[Hentai Assistant] 推送下载';
                downloadBtn.className = 'hdoujin-list-btn';
                downloadBtn.onclick = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    showToast('正在推送 HDoujin 画廊下载任务...', 'info');
                    sendDownload(link.href, "archive");
                };

                // 设置相对定位
                if (container.style.position !== 'relative') {
                    container.style.position = 'relative';
                }

                container.appendChild(downloadBtn);
                processedContainers.add(container);
            });
        });

        // 定期检查新加载的内容（处理分页和动态加载）
        setTimeout(addHDoujinListButtons, 2000);
    }

    // 直接执行页面检测和按钮添加
    if (isNHentaiDetailPage()) {
        // NHentai 详情页代码
        addNHentaiDetailButton();
        observeNHentaiInfoContainer();
    } else if (isNHentaiListPage()) {
        // NHentai 列表页代码
        addNHentaiListButtons();
    } else if (isHDoujinDetailPage()) {
        // HDoujin 详情页代码 - 延迟执行以确保页面加载完成
        setTimeout(() => {
            addHDoujinDetailButton();
            observeHDoujinActionsContainer();
        }, 1000);
    } else if (isHDoujinListPage()) {
        // HDoujin 列表页代码 - 延迟执行以确保页面加载完成
        setTimeout(addHDoujinListButtons, 1000);
    } else {
        if (nhentaiInfoObserver) {
            nhentaiInfoObserver.disconnect();
            nhentaiInfoObserver = null;
        }
        const gd5Element = document.querySelector('#gmid #gd5');
        if (gd5Element) {
            // E-Hentai/ExHentai 详情页代码

            // 创建菜单按钮
            const menuElement = document.createElement('p');
            menuElement.className = 'g2';

            const menuImg = document.createElement('img');
            menuImg.src = 'https://ehgt.org/g/mr.gif';

            const menuLink = document.createElement('a');
            menuLink.href = '#';
            menuLink.textContent = 'Hentai Assistant';

            // 创建二级菜单
            const menu = document.createElement('div');
            menu.style.position = 'absolute';
            menu.style.padding = '5px 0';
            menu.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)';
            menu.style.display = 'none';
            menu.style.zIndex = 9999;
            menu.style.borderRadius = '10px';
            menu.style.minWidth = '180px';

            // 当前是否暗色模式
            let darkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;

            // 应用主题
            function applyTheme() {
                if (darkMode) {
                    menu.style.background = '#2b2b2b';
                    menu.style.border = '1px solid #555';
                    menu.querySelectorAll('div').forEach(item => {
                        item.style.color = '#eee';
                    });
                } else {
                    menu.style.background = '#fff';
                    menu.style.border = '1px solid #ccc';
                    menu.querySelectorAll('div').forEach(item => {
                        item.style.color = '#000';
                    });
                }
            }

            // 菜单项样式
            function styleMenuItem(item) {
                item.style.padding = '5px 20px';
                item.style.cursor = 'pointer';
                item.style.borderRadius = '8px';
                item.onmouseover = () => item.style.background = darkMode ? '#444' : '#eee';
                item.onmouseout = () => item.style.background = '';
                return item;
            }

            // 菜单项函数
            function createMenuItem(text, mode) {
                const item = document.createElement('div');
                item.textContent = text;
                styleMenuItem(item);
                item.onclick = function (e) {
                    menu.style.display = 'none';
                    const currentUrl = window.location.href;
                    sendDownload(currentUrl, mode);
                    e.stopPropagation();
                    return false;
                };
                return item;
            }

            const sendMode1 = createMenuItem('推送种子下载任务', 'torrent');
            const sendMode2 = createMenuItem('推送归档下载任务', 'archive');

            // 菜单项：修改服务器地址
            const editBtn = document.createElement('div');
            editBtn.textContent = '修改服务器地址';
            styleMenuItem(editBtn);
            editBtn.onclick = function (e) {
                menu.style.display = 'none';
                const newBase = prompt('请输入你的 Hentai Assistant 服务地址（如 http://127.0.0.1:5001 ）', SERVER_URL);
                if (newBase) {
                    setSetting('server_url', newBase.replace(/\/$/, ''));
                    showToast('已保存，下次刷新页面生效', 'success');
                }
                e.stopPropagation();
                return false;
            };

            menu.appendChild(sendMode1);
            menu.appendChild(sendMode2);
            menu.appendChild(editBtn);

            document.body.appendChild(menu);

            // 菜单定位在按钮下方
            menuLink.onclick = function (e) {
                const rect = menuLink.getBoundingClientRect();
                menu.style.left = rect.left + window.scrollX + 'px';
                menu.style.top = rect.bottom + window.scrollY + 'px';
                menu.style.display = 'block';
                e.preventDefault();
                e.stopPropagation();
            };

            menu.onclick = (e) => e.stopPropagation();
            document.addEventListener('click', () => menu.style.display = 'none');

            menuElement.appendChild(menuImg);
            menuElement.appendChild(document.createTextNode(' '));
            menuElement.appendChild(menuLink);

            gd5Element.appendChild(menuElement);

            // 监听系统/浏览器主题切换
            const mq = window.matchMedia('(prefers-color-scheme: dark)');
            mq.addEventListener('change', e => {
                darkMode = e.matches;
                applyTheme();
            });

            // 初始应用一次
            applyTheme();
        } else {
            // 列表页面代码
            addListButtons();
        }
    }

    function addListButtons() {
        const trList = document.querySelectorAll(".itg tr, .itg .gl1t");
        if (trList && trList.length) {
            trList.forEach(function (tr) {
                let a = tr.querySelector(".glname a, .gl1e a, .gl1t");
                if (tr.classList.contains('gl1t')) {
                    a = tr.querySelector('a');
                }
                if (!a) return;

                const itemUrl = a.href;

                // 添加下载按钮
                let gldown = tr.querySelector(".gldown");
                if (gldown) {
                    const downloadBtn = document.createElement('div');
                    downloadBtn.textContent = "🡇";
                    downloadBtn.title = "[Hentai Assistant] 推送下载";
                    downloadBtn.className = 'ha-download-btn';
                    downloadBtn.onclick = () => sendDownload(itemUrl, DOWNLOAD_MODE);
                    gldown.appendChild(downloadBtn);
                }
            });
        }
    }
    })();
