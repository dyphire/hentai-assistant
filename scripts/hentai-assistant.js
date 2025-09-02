// ==UserScript==
// @name         Hentai Assistant
// @namespace    http://tampermonkey.net/
// @version      1.5
// @description  Add a "Hentai Assistant" button on e-hentai.org and exhentai.org, with menu
// @author       rosystain
// @match        https://e-hentai.org/*
// @match        https://exhentai.org/*
// @grant        GM_xmlhttpRequest
// @connect      *
// @license      MIT
// ==/UserScript==

(function() {
    'use strict';

    const STORAGE_KEY = 'SERVER_URL';
    const DEFAULT_API_BASE = '';

    let SERVER_URL = localStorage.getItem(STORAGE_KEY) || DEFAULT_API_BASE;

    if (SERVER_URL === DEFAULT_API_BASE) {
        let newBase = '';
        while (!newBase) {
            newBase = prompt('首次使用，请输入你的 Hentai Assistant 服务地址（如 http://127.0.0.1:5001 ）');
            if (newBase === null) break;
        }
        if (newBase) {
            localStorage.setItem(STORAGE_KEY, newBase);
            SERVER_URL = newBase;
            alert('已保存，下次刷新页面生效');
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
    menu.style.background = '#fff';
    menu.style.border = '1px solid #ccc';
    menu.style.padding = '5px 0';
    menu.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)';
    menu.style.display = 'none';
    menu.style.zIndex = 9999;
    menu.style.borderRadius = '10px';

    // 菜单项函数
    function createMenuItem(text, mode) {
        const item = document.createElement('div');
        item.textContent = text;
        item.style.padding = '5px 20px';
        item.style.cursor = 'pointer';
        item.style.borderRadius = '8px';
        item.onmouseover = () => item.style.background = '#eee';
        item.onmouseout = () => item.style.background = '';
        item.onclick = function(e) {
            menu.style.display = 'none';
            const currentUrl = window.location.href;
            const url = `${SERVER_URL}/api/download?url=${encodeURIComponent(currentUrl)}&mode=${mode}`;

            GM_xmlhttpRequest({
                method: 'GET',
                url: url,
                onload: function(response) {
                    try {
                        const data = JSON.parse(response.responseText);
                        if (data && data.task_id) {
                            alert(`已推送下载任务（mode=${mode}），task_id=${data.task_id}`);
                        } else {
                            alert('推送失败：返回数据异常');
                        }
                    } catch (err) {
                        console.error(err, response.responseText);
                        alert('推送失败：返回数据非 JSON');
                    }
                },
                onerror: function(err) {
                    console.error(err);
                    alert('推送失败：请求出错\n请确认服务器地址是否正确');
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
    editBtn.style.padding = '5px 20px';
    editBtn.style.cursor = 'pointer';
    editBtn.style.borderRadius = '8px';
    editBtn.onmouseover = () => editBtn.style.background = '#eee';
    editBtn.onmouseout = () => editBtn.style.background = '';
    editBtn.onclick = function(e) {
        menu.style.display = 'none';
        const newBase = prompt('请输入你的 Hentai Assistant 服务地址（如 http://127.0.0.1:5001 ）', SERVER_URL);
        if (newBase) {
            localStorage.setItem(STORAGE_KEY, newBase);
            SERVER_URL = newBase;
            alert('已保存，下次刷新页面生效');
        }
        e.stopPropagation();
        return false;
    };

    menu.appendChild(sendMode1);
    menu.appendChild(sendMode2);
    menu.appendChild(editBtn);

    document.body.appendChild(menu);

    menuLink.onclick = function(e) {
        menu.style.left = e.clientX + 'px';
        menu.style.top = e.clientY + 'px';
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
})();
