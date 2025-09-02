// ==UserScript==
// @name         Hentai Assistant
// @namespace    http://tampermonkey.net/
// @version      1.6
// @description  Add a "Hentai Assistant" button on e-hentai.org and exhentai.org, with menu
// @author       rosystain
// @match        https://e-hentai.org/*
// @match        https://exhentai.org/*
// @grant        GM_xmlhttpRequest
// @connect      *
// @license      MIT
// ==/UserScript==

(function () {
    'use strict';

    const STORAGE_KEY = 'SERVER_URL';
    const DEFAULT_API_BASE = '';

    let SERVER_URL = localStorage.getItem(STORAGE_KEY) || DEFAULT_API_BASE;

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

    // 首次使用提示输入服务器地址
    if (SERVER_URL === DEFAULT_API_BASE) {
        let newBase = '';
        while (!newBase) {
            newBase = prompt('首次使用，请输入你的 Hentai Assistant 服务地址（如 http://127.0.0.1:5001 ）');
            if (newBase === null) break;
        }
        if (newBase) {
            SERVER_URL = newBase.replace(/\/$/, '');
            localStorage.setItem(STORAGE_KEY, SERVER_URL);
            showToast('已保存，下次刷新页面生效', 'success');
        }
    }

    const gd5Element = document.querySelector('#gmid #gd5');
    if (!gd5Element) return;

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
            const url = `${SERVER_URL}/api/download?url=${encodeURIComponent(currentUrl)}&mode=${mode}`;

            GM_xmlhttpRequest({
                method: 'GET',
                url: url,
                onload: function (response) {
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
            SERVER_URL = newBase.replace(/\/$/, '');
            localStorage.setItem(STORAGE_KEY, SERVER_URL);
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
})();
