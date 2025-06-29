// ==UserScript==
// @name         Hentai Assistant
// @namespace    http://tampermonkey.net/
// @version      1.4
// @description  Add a "Hentai Assistant" button on e-hentai.org and exhentai.org, with menu
// @author       rosystain
// @match        https://e-hentai.org/*
// @match        https://exhentai.org/*
// @grant        none
// @license      MIT
// ==/UserScript==

(function() {
    'use strict';

    const STORAGE_KEY = 'SERVER_URL';
    const DEFAULT_API_BASE = '';

    // 获取API地址（优先localStorage）
    let SERVER_URL = localStorage.getItem(STORAGE_KEY) || DEFAULT_API_BASE;

    // 首次使用强制要求用户设置API地址
    if (SERVER_URL === DEFAULT_API_BASE) {
        let newBase = '';
        while (!newBase) {
            newBase = prompt('首次使用，请输入你的 Hentai Assistant 服务地址（如 http://127.0.0.1:5001 ）');
        }
        localStorage.setItem(STORAGE_KEY, newBase);
        SERVER_URL = newBase;
        alert('已保存，下次刷新页面生效');
    }

    // 插入按钮
    const gd5Element = document.querySelector('#gmid #gd5');
    if (gd5Element) {
        const newElement = document.createElement('p');
        newElement.className = 'g2';

        const imgElement = document.createElement('img');
        imgElement.src = 'https://ehgt.org/g/mr.gif';

        const linkElement = document.createElement('a');
        linkElement.id = 'renamelink';
        linkElement.href = '#';
        linkElement.textContent = 'Hentai Assistant';

        // 创建圆角二级菜单
        const menu = document.createElement('div');
        menu.style.position = 'absolute';
        menu.style.background = '#fff';
        menu.style.border = '1px solid #ccc';
        menu.style.padding = '5px 0';
        menu.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)';
        menu.style.display = 'none';
        menu.style.zIndex = 9999;
        menu.style.borderRadius = '10px'; // 圆角

        // 菜单项：发送
        const sendBtn = document.createElement('div');
        sendBtn.textContent = '推送下载任务';
        sendBtn.style.padding = '5px 20px';
        sendBtn.style.cursor = 'pointer';
        sendBtn.style.borderRadius = '8px';
        sendBtn.onmouseover = () => sendBtn.style.background = '#eee';
        sendBtn.onmouseout = () => sendBtn.style.background = '';
        sendBtn.onclick = function(e) {
            menu.style.display = 'none';
            const currentUrl = window.location.href;
            const HentaiAssistantUrl = `${localStorage.getItem(STORAGE_KEY) || DEFAULT_API_BASE}/api/download?url=${encodeURIComponent(currentUrl)}`;
            window.location.href = HentaiAssistantUrl;
            e.stopPropagation();
            return false;
        };

        // 菜单项：修改服务器
        const editBtn = document.createElement('div');
        editBtn.textContent = '修改服务器地址';
        editBtn.style.padding = '5px 20px';
        editBtn.style.cursor = 'pointer';
        editBtn.style.borderRadius = '8px';
        editBtn.onmouseover = () => editBtn.style.background = '#eee';
        editBtn.onmouseout = () => editBtn.style.background = '';
        editBtn.onclick = function(e) {
            menu.style.display = 'none';
            const newBase = prompt('请输入你的 Hentai Assistant 服务地址（如 http://127.0.0.1:5001 ）', localStorage.getItem(STORAGE_KEY) || DEFAULT_API_BASE);
            if (newBase) {
                localStorage.setItem(STORAGE_KEY, newBase);
                alert('已保存，下次刷新页面生效');
            }
            e.stopPropagation();
            return false;
        };

        menu.appendChild(sendBtn);
        menu.appendChild(editBtn);
        document.body.appendChild(menu);

        linkElement.onclick = function(e) {
            // 菜单定位到鼠标处
            menu.style.left = e.pageX + 'px';
            menu.style.top = e.pageY + 'px';
            menu.style.display = 'block';
            // 点击其他地方关闭菜单
            document.addEventListener('click', function hideMenu() {
                menu.style.display = 'none';
                document.removeEventListener('click', hideMenu);
            });
            e.preventDefault();
            e.stopPropagation();
            return false;
        };

        newElement.appendChild(imgElement);
        newElement.appendChild(document.createTextNode(' '));
        newElement.appendChild(linkElement);

        gd5Element.appendChild(newElement);
    }
})();