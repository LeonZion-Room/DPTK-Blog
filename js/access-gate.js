/*!
 * access-gate.js —— 名片访问口令校验（会话级）
 *
 * 归档：Leon-Note > 【项目】汇总 > WeChat-Card
 * 部署：动态站(Flask) 与 静态站(Cloudflare Pages) 共用本文件
 *       —— 必须登记进 server/static_export.py 的 STATIC_FILES，否则导出后缺失。
 *
 * 设计要点：
 *  1) 口令不明文存放：比对 SHA-256 摘要（crypto.subtle），源码里只有哈希。
 *  2) 会话级：解锁状态写 sessionStorage，关闭标签页即失效；换设备需重新输入。
 *  3) 纯前端门槛，不是安全边界：只挡随手转发，挡不住查看源码的人。
 *  4) 必须在 main-dynamic.js 之前加载（本脚本在 <head>），才能先于页面内容渲染拦截。
 */
(function () {
  'use strict';

  /* ================= 配置 ================= */
  var CONFIG = {
    // 口令 "WSWwsw1234@" 的 SHA-256。改口令：
    //   python3 -c "import hashlib;print(hashlib.sha256(b'新口令').hexdigest())"
    PASS_HASH: '953017ef907fa1e62cd6a44cd7b061fa7a36161913d937add2fdb717341ff5b1',
    STORAGE_KEY: 'dptk_card_unlocked',
    NOTICE_KEY: 'dptk_notice_dismissed',
    GATE_FLAG: 'dptkGateHandled',
    TITLE: '访问验证',
    NOTICE_TITLE: '公告',
    NOTICE_BODY: '由于个人权限相关机制，现需要输入口令才可进行下一步操作。',
    SUB: '请输入访问口令以查看名片',
    PLACEHOLDER: '请输入口令',
    ERR: '口令不正确，请重新输入',
    BTN_OK: '确认',
    BTN_CANCEL: '取消'
  };

  if (window.__DPTK_GATE__) { return; }        // 防重复加载
  window.__DPTK_GATE__ = true;

  /* ================= 工具 ================= */
  function sha256(str) {
    if (window.crypto && window.crypto.subtle && window.TextEncoder) {
      return window.crypto.subtle
        .digest('SHA-256', new TextEncoder().encode(str))
        .then(function (buf) {
          var h = '';
          new Uint8Array(buf).forEach(function (b) {
            h += ('0' + b.toString(16)).slice(-2);
          });
          return h;
        });
    }
    // http 下 crypto.subtle 不可用（Pages 是 https，正常走不到这里）
    return Promise.resolve(null);
  }

  function isUnlocked() {
    try { return sessionStorage.getItem(CONFIG.STORAGE_KEY) === '1'; }
    catch (e) { return false; }
  }
  function setUnlocked() {
    try { sessionStorage.setItem(CONFIG.STORAGE_KEY, '1'); } catch (e) {}
  }

  function styleEl() {
    var s = document.createElement('style');
    s.textContent = [
      '.dptk-gate-mask{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;',
      'justify-content:center;padding:20px;background:rgba(15,23,42,.62);',
      'backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);font-family:-apple-system,',
      'BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB",Roboto,Arial,sans-serif}',
      '.dptk-gate-box{width:100%;max-width:360px;background:#fff;border-radius:18px;padding:26px 24px 22px;',
      'box-shadow:0 24px 60px rgba(0,0,0,.34);text-align:center;',
      'animation:dptkGateIn .22s cubic-bezier(.2,.8,.2,1)}',
      '@keyframes dptkGateIn{from{opacity:0;transform:translateY(14px) scale(.97)}to{opacity:1;transform:none}}',
      '.dptk-gate-ico{width:52px;height:52px;margin:0 auto 14px;border-radius:50%;display:flex;',
      'align-items:center;justify-content:center;background:linear-gradient(135deg,#22d3ee,#4f46e5);',
      'box-shadow:0 8px 20px rgba(79,70,229,.32);font-size:25px;color:#fff}',
      '.dptk-gate-h{font-size:17px;font-weight:700;color:#0f172a;margin-bottom:8px}',
      '.dptk-gate-p{font-size:13.5px;line-height:1.7;color:#64748b;margin-bottom:18px;',
      'overflow-wrap:break-word;word-break:break-word}',
      '.dptk-gate-in{width:100%;padding:12px 14px;font-size:15px;border:1px solid #dbe3ec;',
      'border-radius:11px;outline:none;text-align:center;letter-spacing:.5px;background:#f8fafc;',
      'transition:border-color .18s,box-shadow .18s}',
      '.dptk-gate-in:focus{border-color:#4f46e5;background:#fff;box-shadow:0 0 0 3px rgba(79,70,229,.14)}',
      '.dptk-gate-err{min-height:18px;margin-top:9px;font-size:12.5px;color:#dc2626;line-height:1.4}',
      '.dptk-gate-btns{display:flex;gap:10px;margin-top:14px}',
      '.dptk-gate-btn{flex:1;padding:11px 0;font-size:14.5px;font-weight:600;border-radius:11px;',
      'border:none;cursor:pointer;transition:transform .12s,filter .18s}',
      '.dptk-gate-btn:active{transform:translateY(1px)}',
      '.dptk-gate-ok{background:linear-gradient(135deg,#22d3ee,#4f46e5);color:#fff;',
      'box-shadow:0 6px 16px rgba(79,70,229,.3)}',
      '.dptk-gate-ok:hover{filter:brightness(1.06)}',
      '.dptk-gate-no{background:#f1f5f9;color:#475569}',
      '.dptk-gate-no:hover{background:#e2e8f0}',
      /* 公告条 */
      '.dptk-notice{position:relative;max-width:1200px;margin:0 auto 18px;padding:14px 46px 14px 16px;',
      'display:flex;gap:11px;align-items:flex-start;background:linear-gradient(135deg,#fff7ed,#fef2f2);',
      'border:1px solid #fed7aa;border-left:4px solid #f97316;border-radius:14px;',
      'box-shadow:0 6px 18px rgba(249,115,22,.12);font-size:13.5px;line-height:1.75;color:#7c2d12;',
      'overflow-wrap:break-word;word-break:break-word}',
      '.dptk-notice b{display:block;font-size:14px;margin-bottom:3px;color:#9a3412}',
      '.dptk-notice-x{position:absolute;top:8px;right:10px;width:28px;height:28px;border:none;',
      'background:transparent;color:#c2410c;font-size:19px;line-height:1;cursor:pointer;border-radius:50%}',
      '.dptk-notice-x:hover{background:rgba(249,115,22,.14)}',
      '@media(max-width:640px){.dptk-notice{padding:12px 42px 12px 13px;font-size:12.5px}}'
    ].join('');
    document.head.appendChild(s);
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function overlay(inner) {
    var mask = document.createElement('div');
    mask.className = 'dptk-gate-mask';
    mask.innerHTML = '<div class="dptk-gate-box">' + inner + '</div>';
    // 遮罩内点击不穿透到下层卡片
    mask.addEventListener('click', function (e) { e.stopPropagation(); });
    document.body.appendChild(mask);
    document.documentElement.style.overflow = 'hidden';
    return mask;
  }

  function close(mask) {
    if (mask && mask.parentNode) { mask.parentNode.removeChild(mask); }
    if (!document.querySelector('.dptk-gate-mask')) {
      document.documentElement.style.overflow = '';
    }
  }

  /* ================= 口令弹窗 ================= */
  /**
   * @param {Function} onOk  校验通过后回调
   * @param {Function} [onCancel] 取消回调
   */
  function askPasscode(onOk, onCancel) {
    var mask = overlay(
      '<div class="dptk-gate-ico">&#128274;</div>' +
      '<div class="dptk-gate-h">' + esc(CONFIG.TITLE) + '</div>' +
      '<div class="dptk-gate-p">' + esc(CONFIG.NOTICE_BODY) + '<br>' + esc(CONFIG.SUB) + '</div>' +
      '<input class="dptk-gate-in" type="password" autocomplete="off" ' +
      'inputmode="text" placeholder="' + esc(CONFIG.PLACEHOLDER) + '">' +
      '<div class="dptk-gate-err"></div>' +
      '<div class="dptk-gate-btns">' +
      '<button class="dptk-gate-btn dptk-gate-no" type="button">' + esc(CONFIG.BTN_CANCEL) + '</button>' +
      '<button class="dptk-gate-btn dptk-gate-ok" type="button">' + esc(CONFIG.BTN_OK) + '</button>' +
      '</div>'
    );
    var input = mask.querySelector('.dptk-gate-in');
    var err = mask.querySelector('.dptk-gate-err');
    var ok = mask.querySelector('.dptk-gate-ok');
    var no = mask.querySelector('.dptk-gate-no');

    function submit() {
      var v = input.value.trim();
      if (!v) { err.textContent = '请输入口令'; return; }
      ok.disabled = true;
      ok.textContent = '验证中…';
      sha256(v).then(function (h) {
        if (h && h === CONFIG.PASS_HASH) {
          setUnlocked();
          close(mask);
          onOk && onOk();
        } else {
          err.textContent = CONFIG.ERR;
          input.value = '';
          input.focus();
          ok.disabled = false;
          ok.textContent = CONFIG.BTN_OK;
          input.animate(
            [{ transform: 'translateX(0)' }, { transform: 'translateX(-7px)' },
             { transform: 'translateX(7px)' }, { transform: 'translateX(0)' }],
            { duration: 260 }
          );
        }
      });
    }

    ok.addEventListener('click', submit);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); submit(); }
    });
    no.addEventListener('click', function () {
      close(mask);
      onCancel && onCancel();
    });
    setTimeout(function () { try { input.focus(); } catch (e) {} }, 60);
  }

  /* ================= 公告条 ================= */
  function renderNotice() {
    if (document.querySelector('.dptk-notice')) { return; }
    var wrap = document.querySelector('.wrap') || document.body;
    var box = document.createElement('div');
    box.className = 'dptk-notice';
    box.innerHTML =
      '<button class="dptk-notice-x" type="button" aria-label="关闭">&times;</button>' +
      '<span>&#128276;</span>' +
      '<div><b>' + esc(CONFIG.NOTICE_TITLE) + '</b>' + esc(CONFIG.NOTICE_BODY) + '</div>';
    box.querySelector('.dptk-notice-x').addEventListener('click', function () {
      box.parentNode && box.parentNode.removeChild(box);
      try { sessionStorage.setItem(CONFIG.NOTICE_KEY, '1'); } catch (e) {}
    });
    // 插到 hero 之后；没有 hero 就放最前
    var hero = wrap.querySelector('.hero');
    if (hero && hero.nextSibling) { wrap.insertBefore(box, hero.nextSibling); }
    else if (hero) { wrap.appendChild(box); }
    else { wrap.insertBefore(box, wrap.firstChild); }
  }

  /* ================= 首页：劫持卡片点击 ================= */
  function bindHomeCards() {
    // 事件委托：卡片是模板渲染的 <a class="item" href="/p/xxx/">，动态新增也生效
    document.addEventListener('click', function (e) {
      if (isUnlocked()) { return; }
      var a = e.target && e.target.closest ? e.target.closest('a.item') : null;
      if (!a) { return; }
      var href = a.getAttribute('href');
      if (!href) { return; }
      e.preventDefault();
      e.stopPropagation();
      askPasscode(function () {
        setUnlocked();
        window.location.href = href;
      });
    }, true); // 捕获阶段，抢在 main-dynamic.js 的 handler 之前
  }

  /* ================= 名片页：进页面先拦一道 ================= */
  function gateCardPage() {
    if (isUnlocked()) { return; }
    // 先冻结渲染，避免口令弹窗背后已经把名片画出来了
    var veil = document.createElement('div');
    veil.className = 'dptk-gate-mask';
    veil.innerHTML =
      '<div class="dptk-gate-box" style="box-shadow:none;background:transparent">' +
      '<div class="dptk-gate-ico">&#128274;</div></div>';
    document.body.appendChild(veil);
    document.documentElement.style.overflow = 'hidden';

    askPasscode(
      function () { setUnlocked(); close(veil); },
      function () { window.history.back(); }   // 取消：退回上一页
    );
  }

  /* ================= 入口 ================= */
  function boot() {
    styleEl();

    var path = location.pathname;
    var isHome = /\/home\/?$/.test(path) || path === '/' || path === '/index.html';
    var isCardPage = /^\/p\/[^/]+\/?$/.test(path) ||
                     /index-dynamic\.html/.test(path);

    if (isHome) {
      bindHomeCards();
      try {
        if (sessionStorage.getItem(CONFIG.NOTICE_KEY) !== '1') { renderNotice(); }
      } catch (e) { renderNotice(); }
    } else if (isCardPage) {
      gateCardPage();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  // 供控制台调试：window.DPTKGate.reset()
  window.DPTKGate = { reset: function () {
    try { sessionStorage.removeItem(CONFIG.STORAGE_KEY);
          sessionStorage.removeItem(CONFIG.NOTICE_KEY); } catch (e) {}
  }};
})();
