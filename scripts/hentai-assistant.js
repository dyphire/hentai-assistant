// ==UserScript==
// @name         Hentai Assistant
// @namespace    http://tampermonkey.net/
// @version      1.7
// @description  Add a "Hentai Assistant" button on e-hentai.org and exhentai.org, with menu
// @author       rosystain
// @match        https://e-hentai.org/*
// @match        https://exhentai.org/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_registerMenuCommand
// @require      https://openuserjs.org/src/libs/sizzle/GM_config.js
// @license      MIT
// ==/UserScript==

(function () {
    'use strict';

    console.log('Hentai Assistant script loaded');
    console.log('Current URL:', window.location.href);
    console.log('Host:', window.location.host);
    console.log('Pathname:', window.location.pathname);

    const IS_EX = window.location.host.includes("exhentai");

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

            if (url) {
                setSetting('server_url', url.replace(/\/$/, ''));
                setSetting('download_mode', mode);
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

    console.log('Settings loaded:', { SERVER_URL, DOWNLOAD_MODE });


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
            console.log('sendDownload called with url:', url, 'mode:', mode);
            if (!SERVER_URL) {
                showToast('请先设置服务器地址', 'error');
                return;
            }
            const apiUrl = `${SERVER_URL}/api/download?url=${encodeURIComponent(url)}&mode=${mode}`;
            console.log('apiUrl:', apiUrl);
        GM_xmlhttpRequest({
            method: 'GET',
            url: apiUrl,
            onload: function (response) {
                console.log('Response:', response);
                try {
                    const data = JSON.parse(response.responseText);
                    if (data && data.task_id) {
                        showToast(`已推送下载任务（mode=${mode}），task_id=${data.task_id}`, 'success');
                    } else {
                        showToast('推送失败：返回数据异常', 'error');
                    }
                } catch (err) {
                    console.error(err, response.responseText);
                    showToast('推送失败：返回数据非 JSON', 'error');
                }
            },
            onerror: function (err) {
                console.error(err);
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
    `;
    document.head.appendChild(style);


    console.log('Checking page type');
    const gd5Element = document.querySelector('#gmid #gd5');
    if (gd5Element) {
        console.log('Detail page detected');
        // 详情页代码

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
        console.log('List page detected');
        // 列表页面代码
        addListButtons();
    }

    function addListButtons() {
        console.log('addListButtons called');
        const trList = document.querySelectorAll(".itg tr, .itg .gl1t");
        console.log('trList:', trList);
        if (trList && trList.length) {
            console.log('Found trList with length:', trList.length);
            trList.forEach(function (tr) {
                let a = tr.querySelector(".glname a, .gl1e a, .gl1t");
                if (tr.classList.contains('gl1t')) a = tr.querySelector('a');
                if (!a) return;
                const itemUrl = a.href;
                let gldown = tr.querySelector(".gldown");
                console.log('gldown:', gldown);
                if (gldown) {
                    const downloadBtn = document.createElement('div');
                    downloadBtn.textContent = "🡇";
                    downloadBtn.title = "[Hentai Assistant] 推送下载";
                    downloadBtn.className = 'ha-download-btn';
                    downloadBtn.onclick = () => {
                        console.log('Button clicked, itemUrl:', itemUrl);
                        sendDownload(itemUrl, DOWNLOAD_MODE);
                    };
                    gldown.appendChild(downloadBtn);
                }
            });
        }
        }
    })();

