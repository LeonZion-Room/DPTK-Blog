(function() {
  'use strict';

  const DynamicConfig = {
    config: null,
    serverUrl: '',
    currentNotice: null,
    FETCH_TIMEOUT: 8000, // 8秒超时
    _initialized: false,
    _initPromise: null,
    _carouselIntervals: [],
    _carouselResizeHandlers: [],
    _cleanupRegistered: false,
    _pendingRequests: new Map(), // 请求去重

    // 注册页面清理钩子，防止多标签页内存泄漏
    _registerCleanup() {
      if (this._cleanupRegistered) return;
      this._cleanupRegistered = true;
      const cleanup = () => {
        this._carouselIntervals.forEach(id => clearInterval(id));
        this._carouselIntervals = [];
        this._carouselResizeHandlers.forEach(fn => window.removeEventListener('resize', fn));
        this._carouselResizeHandlers = [];
      };
      window.addEventListener('pagehide', cleanup);
      window.addEventListener('beforeunload', cleanup);
      // 页面隐藏时清理（多标签页切换场景）
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') cleanup();
      });
    },

    // 带超时的fetch
    async fetchWithTimeout(url, options = {}, timeout) {
      const t = timeout || this.FETCH_TIMEOUT;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), t);
      try {
        const response = await fetch(url, { ...options, signal: controller.signal });
        return response;
      } finally {
        clearTimeout(timer);
      }
    },

    // 带重试的fetch（3次指数退避），支持请求去重
    async fetchWithRetry(url, options = {}, retries = 3, timeout) {
      // 请求去重：同一URL的并发请求共享同一个Promise
      const cacheKey = url + JSON.stringify(options);
      if (this._pendingRequests.has(cacheKey)) {
        return this._pendingRequests.get(cacheKey);
      }

      const doFetch = async () => {
        for (let i = 0; i < retries; i++) {
          try {
            const response = await this.fetchWithTimeout(url, options, timeout);
            if (response.ok || response.status < 500) return response;
            // 5xx错误才重试
            if (i < retries - 1) {
              await new Promise(r => setTimeout(r, 500 * Math.pow(2, i)));
            }
          } catch (e) {
            if (e.name === 'AbortError' && i < retries - 1) {
              await new Promise(r => setTimeout(r, 500 * Math.pow(2, i)));
              continue;
            }
            if (i === retries - 1) throw e;
            await new Promise(r => setTimeout(r, 500 * Math.pow(2, i)));
          }
        }
        return this.fetchWithTimeout(url, options, timeout);
      };

      const promise = doFetch();
      this._pendingRequests.set(cacheKey, promise);
      try {
        const result = await promise;
        return result;
      } finally {
        this._pendingRequests.delete(cacheKey);
      }
    },

    // 辅助函数：将相对URL或本地IP URL转换为使用serverUrl的绝对URL
    getAbsoluteUrl(url) {
      if (!url) return url;
      // 媒体基地址（直接使用公网IP）
      const mediaBase = 'http://119.145.17.34:8000';
      // 当前页面入口（Cpolar HTTPS，有备案）
      const entryOrigin = window.location.origin;
      if (url.startsWith('http')) {
        // 原站公网地址统一改写为 HTTPS
        if (url.includes('119.145.17.34:8000')) {
          const path = url.replace(/^https?:\/\/[^\/]+/, '');
          // 媒体资源（uploads/pdf 等静态文件）走 leyon.top HTTPS 反代
          if (path.startsWith('/uploads/') || path.startsWith('/pdf/') || path.includes('/static/')) {
            return mediaBase + path;
          }
          // 页面跳转（index-dynamic.html / 根路径 /api 等）保持当前 Cpolar 入口
          return entryOrigin + path;
        }
        // 本地IP URL 替换为当前入口
        if (url.includes('172.168.') || url.includes('192.168.') || url.includes('127.0.0.1') || url.includes('localhost')) {
          const path = url.replace(/^https?:\/\/[^\/]+/, '');
          return entryOrigin + path;
        }
        return url;
      }
      // 非http开头的URL，检查是否是相对路径
      if (url.startsWith('/')) {
        // 媒体相对路径走 leyon.top，其它走当前入口
        if (url.startsWith('/uploads/') || url.startsWith('/pdf/') || url.includes('/static/')) {
          return mediaBase + url;
        }
        return entryOrigin + url;
      } else {
        // 相对路径，添加uploads前缀（媒体走 leyon.top）
        return mediaBase + '/uploads/' + url;
      }
    },

    // 生成模块背景HTML
    getSectionBgHtml(section) {
      const bgTheme = section.bgTheme || '';
      const customBgImage = section.customBgImage || '';
      const customBgColor = section.customBgColor || '';
      const bgScaleMode = section.bgScaleMode || 'cover'; // 'cover' | 'contain' | 'auto' | 'scale-to-fill'

      if (!bgTheme && !customBgImage && !customBgColor) return '';

      let bgStyle = '';
      if (customBgImage) {
        const bgSizeMap = {
          'cover': 'cover',
          'contain': 'contain',
          'auto': 'auto',
          'scale-to-fill': '100% 100%'
        };
        const bgSize = bgSizeMap[bgScaleMode] || 'cover';
        bgStyle = `background-image: url('${this.getAbsoluteUrl(customBgImage)}'); background-size: ${bgSize}; background-position: center; background-repeat: no-repeat;`;
      } else if (customBgColor) {
        bgStyle = `background: ${customBgColor};`;
      } else if (bgTheme) {
        bgStyle = ''; // CSS class will handle theme backgrounds
      }

      const themeClass = bgTheme ? ` section-bg-${bgTheme}` : '';
      const scaleClass = customBgImage ? ` section-bg-${bgScaleMode}` : '';
      return `<div class="section-bg${themeClass}${scaleClass}" style="${bgStyle}"></div>`;
    },

    // Markdown解析函数
    parseMarkdown(md) {
      if (!md) return '';
      let html = md
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
        .replace(/^---$/gm, '<hr>')
        .replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>')
        .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
        .replace(/^- (.+)$/gm, '<li>$1</li>');
      html = html.replace(/(<li>.*<\/li>\n?)+/g, function(m) { return '<ul>' + m + '</ul>'; });
      html = html.replace(/\n{2,}/g, '</p><p>');
      html = html.replace(/\n/g, '<br>');
      if (html && !html.startsWith('<')) html = '<p>' + html + '</p>';
      return html;
    },

    async init() {
      try {
        this._registerCleanup();
        const loaded = await this.loadConfig();
        if (!loaded) {
          this.hideSkeleton();
          return;
        }
        
        // 检查配置是否加载成功
        console.log('Checking config after load:', this.config);
        console.log('CurrentPage:', this.config?.currentPage);
        if (!this.config || !this.config.currentPage) {
          console.error('Config or currentPage is missing!');
          this.hideSkeleton();
          this.showErrorRetry();
          return;
        }
        
        this.setMobileGap();
        this.renderBasicInfo();
        this.renderSections();
        
        // 隐藏骨架屏，显示页面
        this.hideSkeleton();
        
        // 微信分享初始化不阻塞页面渲染
        this.initWechatShare().catch(e => {
          console.error('Wechat share init error:', e);
        });
        
        this.bindEvents();
        this.checkAutoPopupNotice();
        // 延迟处理视频，不阻塞渲染
        setTimeout(() => {
          try {
            this.setupVideoCovers();
          } catch (e) {
            console.error('Video covers setup error:', e);
          }
        }, 1000);
      } catch (e) {
        console.error('Init error:', e);
        this.hideSkeleton();
        this.showErrorRetry();
      }
    },
    
    hideSkeleton() {
      const skeleton = document.getElementById('loadingSkeleton');
      const pageContainer = document.getElementById('pageContainer');
      if (skeleton) skeleton.style.display = 'none';
      if (pageContainer) pageContainer.style.display = 'block';
    },
    
    showErrorRetry() {
      const errorRetry = document.getElementById('errorRetry');
      if (errorRetry) {
        errorRetry.style.display = 'flex';
      }
    },
    
    setMobileGap() {
      const currentPage = this.config.currentPage;
      const mobileGap = (currentPage && currentPage.mobile_gap) || this.config.mobile_gap || 10;
      console.log('Setting mobile gap:', mobileGap);
      const style = document.createElement('style');
      style.textContent = `
        @media screen and (max-width: 480px) {
          .unified-card-wrapper {
            margin: ${mobileGap}px !important;
            border-radius: ${mobileGap + 6}px !important;
          }
        }
      `;
      document.head.appendChild(style);
    },

    async loadConfig() {
      try {
        // 先使用默认域名获取配置
        const defaultServerUrl = window.location.origin;

        // 获取URL中的页面参数
        const urlParams = new URLSearchParams(window.location.search);
        const pageId = urlParams.get('page');
        console.log('Loading config for page:', pageId);

        const url = pageId ?
          defaultServerUrl + '/api/card-config?page=' + pageId :
          defaultServerUrl + '/api/card-config';
        console.log('Fetching URL:', url);

        // 带重试请求
        const response = await this.fetchWithRetry(url);
        if (!response.ok) {
          console.error('Failed to load config, status:', response.status);
          this.showErrorRetry();
          return false;
        }

        this.config = await response.json();
        console.log('Loaded config:', this.config);
        console.log('CurrentPage:', this.config?.currentPage);

        // 使用currentPage的sections
        if (this.config.currentPage) {
          this.config.sections = this.config.currentPage.sections || [];
          console.log('Sections from currentPage:', this.config.sections);
        } else {
          console.error('currentPage is missing from response');
          this.showErrorRetry();
          return false;
        }

        // 设置serverUrl：始终用当前页面入口（Cpolar HTTPS），保证 API/跳转不走混合内容
        this.serverUrl = window.location.origin;

        return true;
      } catch (e) {
        if (e.name === 'AbortError') {
          console.error('Config loading timed out after ' + this.FETCH_TIMEOUT + 'ms');
        } else {
          console.error('Error loading config:', e);
        }
        this.showErrorRetry();
        return false;
      }
    },

    getDefaultConfig() {
      return {
        basicInfo: {
          name: '姓名',
          title: '职位',
          title2: '',
          phone: '电话',
          email: '',
          logo: ''
        },
        sections: [],
        settings: {
          showCallConfirm: true
        }
      };
    },

    getCurrentPage() {
      return this.config?.currentPage || null;
    },

    renderBasicInfo() {
      // 获取当前页面配置
      const currentPage = this.getCurrentPage();

      // 移除之前的主题类
      document.body.className = document.body.className.replace(/bg-theme-\S+/g, '').trim();
      document.body.className = document.body.className.replace(/content-theme-\S+/g, '').trim();
      document.body.className = document.body.className.replace(/page-bg-custom/g, '').trim();

      // 应用页面背景设置
      const pageBgTheme = currentPage?.page_bg_theme || '';
      const pageCustomBgImage = currentPage?.page_custom_bg_image || '';
      const pageBgScaleMode = currentPage?.page_bg_scale_mode || 'cover'; // 'cover' | 'contain' | 'auto' | 'scale-to-fill'

      // 重置页面背景样式
      document.body.className = document.body.className.replace(/page-bg-\S+/g, '').trim();
      document.body.style.background = '';
      document.body.style.backgroundImage = '';
      document.body.style.backgroundSize = '';
      document.body.style.backgroundPosition = '';
      document.body.style.backgroundRepeat = '';
      document.body.style.backgroundAttachment = '';

      if (pageCustomBgImage) {
        // 应用自定义页面背景图片
        document.body.style.backgroundImage = `url('${this.getAbsoluteUrl(pageCustomBgImage)}')`;
        const bgSizeMap = {
          'cover': 'cover',
          'contain': 'contain',
          'auto': 'auto',
          'scale-to-fill': '100% 100%'
        };
        document.body.style.backgroundSize = bgSizeMap[pageBgScaleMode] || 'cover';
        if (pageBgScaleMode === 'contain') {
          document.body.style.backgroundPosition = 'center top';
        } else if (pageBgScaleMode === 'auto') {
          document.body.style.backgroundPosition = 'left top';
        } else {
          document.body.style.backgroundPosition = 'center';
        }
        document.body.style.backgroundRepeat = 'no-repeat';
        document.body.style.backgroundAttachment = 'fixed';
        document.body.classList.add('page-bg-custom', `page-bg-${pageBgScaleMode}`);
      } else if (pageBgTheme) {
        // 应用页面背景主题
        document.body.classList.add(pageBgTheme);
      }

      // ========== 名片信息模块 ==========
      const contactSection = this.config.sections && this.config.sections.find(s => s.type === 'contact');
      const basicInfo = this.config.basicInfo || {};
      const hasMarkdown = basicInfo.markdownContent && basicInfo.markdownContent.trim();

      if (!contactSection && !hasMarkdown) {
        const w = document.querySelector('.info-card-wrapper');
        if (w) w.style.display = 'none';
        return;
      }

      const info = { ...basicInfo, ...contactSection };

      if (info && (contactSection || hasMarkdown)) {
        const infoCard = document.querySelector('.info-card');
        const infoContent = document.querySelector('.info-content');
        const buttonGroup = document.querySelector('.info-card .button-group');

        // --- 1. 背景处理 ---
        if (infoCard) {
          infoCard.style.background = '';
          infoCard.style.backgroundImage = '';
          infoCard.style.backgroundSize = '';
          infoCard.style.backgroundPosition = '';
          infoCard.style.backgroundRepeat = '';
        }

        const cardBgTheme = currentPage?.card_bg_theme || info.bgTheme || info.theme;
        const cardCustomBgImage = currentPage?.card_custom_bg_image || info.customBgImage;

        if (cardCustomBgImage) {
          // 背景图片模式：绝对定位 img 层 + 文字/按钮覆盖
          const absBgUrl = this.getAbsoluteUrl(cardCustomBgImage);
          const preloadImg = new Image();
          preloadImg.onload = () => {
            const imgRatio = preloadImg.naturalWidth / preloadImg.naturalHeight;
            const cardWidth = infoCard ? infoCard.offsetWidth : window.innerWidth;
            const imgDisplayHeight = Math.round(cardWidth / imgRatio);

            const oldBgImg = infoCard?.querySelector('.bg-img-layer');
            if (oldBgImg) oldBgImg.remove();

            if (infoCard) {
              infoCard.classList.add('bg-contain-mode');
              infoCard.style.position = 'relative';
              infoCard.style.height = imgDisplayHeight + 'px';

              const bgImg = document.createElement('img');
              bgImg.className = 'bg-img-layer';
              bgImg.src = absBgUrl;
              bgImg.alt = '';
              infoCard.appendChild(bgImg);

              const wrapper = infoCard.closest('.unified-card-wrapper');
              if (wrapper) wrapper.classList.add('bg-contain-mode');
            }

            // 文字和按钮绝对定位（文字位置固定，按钮位置由 btnTopPercent 按图片高度百分比自适应）
            // 优先使用百分比；若只有旧的 btnTop 像素值，则按图片高度换算为百分比后再定位
            let btnTopPercent = info.btnTopPercent !== undefined ? info.btnTopPercent : null;
            if (btnTopPercent === null && info.btnTop !== undefined) {
              // 旧版像素值：以手机 375px 宽度为参考换算成百分比
              btnTopPercent = Math.round((info.btnTop / (375 / imgRatio)) * 100);
            }
            if (btnTopPercent === null) btnTopPercent = 30;
            const btnTopPx = (btnTopPercent / 100) * imgDisplayHeight;

            if (infoContent) {
              infoContent.style.position = 'absolute';
              infoContent.style.top = '45px';
              infoContent.style.left = '20px';
              infoContent.style.right = '20px';
              infoContent.style.zIndex = '2';
              infoContent.style.margin = '0';
            }
            if (buttonGroup) {
              buttonGroup.style.position = 'absolute';
              buttonGroup.style.top = btnTopPx + 'px';
              buttonGroup.style.left = '20px';
              buttonGroup.style.right = '20px';
              buttonGroup.style.zIndex = '2';
              buttonGroup.style.margin = '0';
            }
          };
          preloadImg.onerror = () => console.error('背景图加载失败:', absBgUrl);
          preloadImg.src = absBgUrl;

          // 背景图模式下的默认文字颜色
          if (infoCard) infoCard.style.color = '#333';
          ['phone','title','title2','email','company','address'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.color = '#333';
          });

          // 按钮默认白色半透明
          document.querySelectorAll('.info-card .btn').forEach(btn => {
            btn.style.background = 'rgba(255,255,255,0.9)';
            btn.style.color = '#333';
            btn.style.boxShadow = '0 4px 15px rgba(0,0,0,0.2)';
          });
        } else if (cardBgTheme) {
          const themeStyles = {
            'theme-purple-pink': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            'theme-blue-green': 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)',
            'theme-orange-red': 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
            'theme-cyan-blue': 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
            'theme-gold': 'linear-gradient(135deg, #f6d365 0%, #fda085 100%)',
            'theme-deep-purple': 'linear-gradient(135deg, #30cfd0 0%, #330867 100%)',
            'theme-dark-purple': 'linear-gradient(135deg, #30cfd0 0%, #330867 100%)',
            'theme-white': 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
            'theme-dark': 'linear-gradient(135deg, #232526 0%, #414345 100%)'
          };
          if (infoCard && themeStyles[cardBgTheme]) {
            infoCard.style.background = themeStyles[cardBgTheme];
          }
        }

        // --- 2. 隐藏个人信息字段（不再使用） ---
        ['name', 'phone', 'title', 'title2', 'email', 'company', 'address'].forEach(id => {
          const el = document.getElementById(id);
          if (el) el.style.display = 'none';
        });
        const mdContentEl = document.getElementById('mdContent');
        if (mdContentEl) mdContentEl.style.display = 'none';

        // --- 5. 按钮配置 ---
        const btnCopy = document.getElementById('btnCopy');
        const btnLink = document.getElementById('btnLink');

        if (info.hideButtons) {
          if (buttonGroup) buttonGroup.style.display = 'none';
        }

        const btnColor = info.btnColor;
        const btnTextColor = info.btnTextColor;
        const btnFontSize = info.btnFontSize !== undefined ? info.btnFontSize : 24;
        const btnGap = info.btnGap !== undefined ? info.btnGap : 10;
        // 按钮背景透明度 0-1（仅影响背景，通过 rgba 实现，不波及文字）
        const btnOpacity = info.btnOpacity !== undefined ? info.btnOpacity : 1;
        // 按钮文字透明度 0-1（仅影响文字，独立于背景透明度）
        const btnTextOpacity = info.btnTextOpacity !== undefined ? info.btnTextOpacity : 1;
        // 按钮字体粗细
        const btnFontWeight = info.btnFontWeight || 700;
        // 按钮高度(px)：配合 btnFontSize 控制文字占按钮的比例（比例 = btnFontSize / btnHeight）
        const btnHeight = info.btnHeight !== undefined ? info.btnHeight : 0;
        // 按钮横向长度（占可用宽度的百分比，如 60 = 60% 宽）
        const btnWidthPercent = info.btnWidthPercent !== undefined ? info.btnWidthPercent : 100;
        // 按钮圆角(px)：配合高度调整外观
        const btnRadius = info.btnRadius !== undefined ? info.btnRadius : 30;

        // hex 转 rgba（用于分离背景/文字透明度）
        const hexToRgba = (hex, alpha) => {
          if (!hex || typeof hex !== 'string') return hex;
          let h = hex.replace('#', '');
          if (h.length === 3) h = h.split('').map(c => c + c).join('');
          if (h.length !== 6) return hex;
          const r = parseInt(h.substr(0, 2), 16);
          const g = parseInt(h.substr(2, 2), 16);
          const b = parseInt(h.substr(4, 2), 16);
          return `rgba(${r}, ${g}, ${b}, ${alpha})`;
        };
        // 带透明度的背景色 / 文字色
        const bgColorWithOpacity = btnColor ? (btnOpacity < 1 ? hexToRgba(btnColor, btnOpacity) : btnColor) : null;
        const textColorWithOpacity = btnTextColor ? (btnTextOpacity < 1 ? hexToRgba(btnTextColor, btnTextOpacity) : btnTextColor) : null;

        // 统一应用按钮样式
        document.querySelectorAll('.info-card .btn').forEach(btn => {
          if (bgColorWithOpacity) {
            btn.style.background = bgColorWithOpacity;
            btn.style.boxShadow = btnOpacity < 1
              ? `0 10px 30px ${hexToRgba(btnColor, 0.4 * btnOpacity)}, 0 4px 12px ${hexToRgba(btnColor, 0.2 * btnOpacity)}`
              : `0 10px 30px ${btnColor}66, 0 4px 12px ${btnColor}33`;
          }
          if (textColorWithOpacity) btn.style.color = textColorWithOpacity;
          btn.style.fontSize = btnFontSize + 'px';
          btn.style.fontWeight = btnFontWeight;
          // 未设置 btnColor（使用主题渐变）时，btnOpacity 退化为整体透明度
          if (!bgColorWithOpacity && btnOpacity < 1) {
            btn.style.opacity = btnOpacity;
          } else {
            btn.style.opacity = '';
          }
          // 按钮高度：固定高度 + 行高垂直居中，控制文字占比
          if (btnHeight > 0) {
            btn.style.height = btnHeight + 'px';
            btn.style.padding = '0 12px';
            btn.style.lineHeight = btnHeight + 'px';
          }
          // 按钮横向长度：占可用宽度百分比（btnWidthPercent）
          // 注意：CSS .btn 默认 flex:1 会覆盖 width，必须同时禁用 flex 拉伸
          const btnW = Math.min(100, Math.max(1, btnWidthPercent));
          if (btnW >= 100) {
            btn.style.width = '';
            btn.style.flex = '1 1 0%';
          } else {
            btn.style.width = btnW + '%';
            btn.style.flex = '0 0 auto';
          }
          btn.style.borderRadius = btnRadius + 'px';
        });
        if (buttonGroup) {
          buttonGroup.style.gap = btnGap + 'px';
          // 按钮宽度小于100%时，改为居中对齐（配合 flex:0 0 auto 实现居中短按钮）
          const groupBtnW = Math.min(100, Math.max(1, btnWidthPercent));
          buttonGroup.style.justifyContent = groupBtnW < 100 ? 'center' : 'space-around';
        }

        // 按钮1跳转链接
        if (info.btn1Jump && info.btn1Jump.trim()) {
          if (btnCopy) btnCopy.style.display = 'none';
          if (btnLink) {
            btnLink.style.display = 'inline-block';
            btnLink.href = info.btn1Jump;
            btnLink.textContent = info.btn1Text || '了解更多';
            if (bgColorWithOpacity) {
              btnLink.style.background = bgColorWithOpacity;
              btnLink.style.boxShadow = btnOpacity < 1
                ? `0 10px 30px ${hexToRgba(btnColor, 0.4 * btnOpacity)}, 0 4px 12px ${hexToRgba(btnColor, 0.2 * btnOpacity)}`
                : `0 10px 30px ${btnColor}66, 0 4px 12px ${btnColor}33`;
            }
            if (textColorWithOpacity) btnLink.style.color = textColorWithOpacity;
            btnLink.style.fontSize = btnFontSize + 'px';
            btnLink.style.fontWeight = btnFontWeight;
            if (btnHeight > 0) {
              btnLink.style.height = btnHeight + 'px';
              btnLink.style.padding = '0 12px';
              btnLink.style.lineHeight = btnHeight + 'px';
            }
            const btnLinkW = Math.min(100, Math.max(1, btnWidthPercent));
            if (btnLinkW >= 100) {
              btnLink.style.width = '';
              btnLink.style.flex = '1 1 0%';
            } else {
              btnLink.style.width = btnLinkW + '%';
              btnLink.style.flex = '0 0 auto';
            }
            btnLink.style.borderRadius = btnRadius + 'px';
          }
        } else {
          if (btnCopy) btnCopy.style.display = 'inline-block';
          if (btnLink) btnLink.style.display = 'none';
        }
        
        // 解析页面标题，提取最后两个属性
        let pageTitle = '微信名片';
        if (currentPage && currentPage.title) {
          const attrs = currentPage.title.split('-').map(s => s.trim()).filter(s => s);
          if (attrs.length >= 2) {
            pageTitle = attrs[attrs.length - 2] + ' - ' + attrs[attrs.length - 1];
          } else if (attrs.length === 1) {
            pageTitle = attrs[0];
          }
        }
        document.title = pageTitle;
        
        // 显示名片信息部分
        const infoCardWrapper = document.querySelector('.info-card-wrapper');
        if (infoCardWrapper) {
          infoCardWrapper.style.display = 'block';
        }
      } else {
        // 没有名片信息组件，使用默认主题并隐藏名片信息部分
        document.body.classList.add('bg-theme-white');
        document.body.classList.add('content-theme-purple-pink');
        const infoCardWrapper = document.querySelector('.info-card-wrapper');
        if (infoCardWrapper) {
          infoCardWrapper.style.display = 'none';
        }
        document.title = '微信名片';
      }
    },

    renderSections() {
      const container = document.getElementById('contentSections');
      if (!container) return;
      
      // 如果没有sections，直接返回
      if (!this.config.sections || !Array.isArray(this.config.sections) || this.config.sections.length === 0) {
        return;
      }
      
      let html = '';
      
      // 获取名片信息中的logo
      const contactSection = this.config.sections.find(section => section.type === 'contact');
      const logoUrl = contactSection ? contactSection.logo : '';
      
      // 如果只有名片信息组件，没有其他内容，直接返回
      const contentSections = this.config.sections.filter(section => section.type !== 'contact');
      if (contentSections.length === 0) {
        return;
      }

      this.config.sections.forEach((section, index) => {
        // 跳过名片信息组件，因为已经在renderBasicInfo中处理
        if (section.type === 'contact') {
          return;
        }
        // 生成外间距、内边距和圆角样式
        const margin = section.margin !== undefined ? section.margin : 0;
        const padding = 0;
        const borderRadius = section.borderRadius !== undefined ? section.borderRadius : 0;
        const borderRadiusStyle = `border-radius: ${borderRadius}px !important;`;
        const fullContainerStyle = `style="margin-left: ${margin}px !important; margin-right: ${margin}px !important; margin-top: 0 !important; margin-bottom: 0 !important; padding: 0 !important; width: calc(100% - ${margin * 2}px) !important; ${borderRadiusStyle}"`;
        // mdContact 在 renderSections 中渲染为独立卡片
        if (section.type === 'mdContact') {
          html += this.renderMdContactSection(section, fullContainerStyle, borderRadiusStyle);
          return;
        }
        
        // 检查是否有模块级背景设置
        const hasSectionBg = section.bgTheme || section.customBgImage || section.customBgColor;
        const sectionBgHtml = hasSectionBg ? this.getSectionBgHtml(section) : '';
        
        // 为标题组件创建特殊的样式（标题使用 titleBorderRadius）
        const titleBorderRadius = section.titleBorderRadius !== undefined ? section.titleBorderRadius : 0;
        const titleBorderRadiusStyle = titleBorderRadius > 0 ? `border-radius: ${titleBorderRadius}px !important; overflow: hidden;` : borderRadiusStyle;
        let containerStyle = `style="margin-left: ${margin}px !important; margin-right: ${margin}px !important; margin-top: 0 !important; margin-bottom: 0 !important; width: calc(100% - ${margin * 2}px) !important; ${titleBorderRadiusStyle}"`;
        
        // 生成模块内容HTML
        let sectionContentHtml = '';
        switch (section.type) {
          case 'title':
            sectionContentHtml = this.renderTitleSection(section, logoUrl, containerStyle);
            break;
          case 'image':
            const imageId = 'image_' + Date.now() + Math.floor(Math.random() * 1000);
            sectionContentHtml = '<div ' + fullContainerStyle + ' data-jump="' + (this.getAbsoluteUrl(section.jump) || '') + '" data-zoomable="' + (section.zoomable ? 'true' : 'false') + '">' +
                    '<img id="' + imageId + '" class="clickable-resource" data-res-url="' + this.getAbsoluteUrl(section.src) + '" src="' + this.getAbsoluteUrl(section.src) + '"  alt="" loading="lazy" style="width: 100%; height: auto; object-fit: contain; display: block;">' +
                    '</div>';
            break;
          case 'video':
            const videoId = 'video_' + Date.now() + Math.floor(Math.random() * 1000);
            sectionContentHtml = '<div ' + fullContainerStyle + '>' +
                    '<video id="' + videoId + '" src="' + this.getAbsoluteUrl(section.src) + '" poster="' + (this.getAbsoluteUrl(section.poster) || '') + '" controls playsinline webkit-playsinline preload="none" style="width: 100%; height: auto; object-fit: contain; display: block;"></video>' +
                    '</div>';
            break;
          case 'grid':
            const gridPadding = section.padding !== undefined ? section.padding : 0;
            const gridGap = section.gap !== undefined ? section.gap : 4;
            const gridBorderRadius = 0; // 强制为0消除间隙
            sectionContentHtml = '<div ' + fullContainerStyle + '>';
            sectionContentHtml += '<div class="image-grid" style="--grid-padding: ' + gridPadding + 'px; --grid-gap: ' + gridGap + 'px; border-radius: ' + gridBorderRadius + 'px; overflow: hidden;">';
            section.images.forEach((img) => {
              sectionContentHtml += '<div class="image-grid-item" data-jump="' + (this.getAbsoluteUrl(img.jump) || '') + '">' +
                      '<img class="clickable-resource" data-res-url="' + this.getAbsoluteUrl(img.src) + '" src="' + this.getAbsoluteUrl(img.src) + '"  alt="" loading="lazy">' +
                      '</div>';
            });
            sectionContentHtml += '</div>';
            sectionContentHtml += '</div>';
            break;
          case 'carousel':
            sectionContentHtml = this.renderCarouselSection(section, fullContainerStyle, borderRadiusStyle);
            break;
          case 'tabs':
            sectionContentHtml = this.renderTabsSection(section, index, fullContainerStyle, borderRadiusStyle);
            break;
          case 'iconRow':
            sectionContentHtml = this.renderIconRowSection(section, fullContainerStyle, borderRadiusStyle);
            break;
          case 'notice':
            sectionContentHtml = this.renderNoticeCard(section, fullContainerStyle, borderRadiusStyle);
            break;
          case 'code':
            sectionContentHtml = '<div ' + fullContainerStyle + '>';
            if (section.html) {
              sectionContentHtml += section.html;
            }
            if (section.js) {
              sectionContentHtml += '<script>' + section.js + '</script>';
            }
            if (section.css) {
              sectionContentHtml += '<style>' + section.css + '</style>';
            }
            sectionContentHtml += '</div>';
            break;
          case 'spacer':
            const spacerHeight = section.height || 20;
            sectionContentHtml = '<div class="spacer-section" style="height: ' + spacerHeight + 'px; width: 100%;"></div>';
            break;
          case 'pdf':
            const pdfHeight = section.height || 600;
            const pdfId = 'pdf-container-' + Date.now() + Math.floor(Math.random() * 1000);
            sectionContentHtml = '<div class="pdf-section" style="width: 100%;">' +
                    '<div class="pdf-viewer" id="' + pdfId + '" style="width: 100%; background: #f7fafc; border-radius: 8px; overflow: hidden;"></div>' +
                    '</div>';
            setTimeout(() => {
              this.renderPDF(this.getAbsoluteUrl(section.src), pdfId, pdfHeight);
            }, 100);
            break;
          case 'footer':
            const footerMargin = section.margin !== undefined ? section.margin : 0;
            sectionContentHtml = '<div class="footer-section" style="margin-left: ' + footerMargin + 'px; margin-right: ' + footerMargin + 'px; margin-top: 0; margin-bottom: 0; padding: 0; width: calc(100% - ' + (footerMargin * 2) + 'px);">' +
                    '<img class="clickable-resource" data-res-url="' + this.getAbsoluteUrl(section.src) + '" src="' + this.getAbsoluteUrl(section.src) + '"  alt="" loading="lazy" style="width: 100%; height: auto; object-fit: cover; border-radius: 0;">' +
                    '</div>';
            break;
          case 'imageGridLink':
            sectionContentHtml = this.renderImageGridLinkSection(section, fullContainerStyle);
            break;
          case 'imageButton':
            sectionContentHtml = this.renderImageButtonSection(section, fullContainerStyle);
            break;
          case 'mapping':
            // 正常情况下服务端已解析为被引用组件内容；此处兜底展示
            const refIds = (section.refUids && section.refUids.length) ? section.refUids : (section.refUid ? [section.refUid] : []);
            const mappedText = refIds.length
              ? `映射组件 ${refIds.join(', ')} 未解析，请刷新重试`
              : '映射组件未设置引用ID';
            sectionContentHtml = '<div ' + fullContainerStyle + '>' +
              `<div style="padding:16px;text-align:center;color:#999;font-size:14px;">${mappedText}</div>` +
              '</div>';
            break;
        }
        
        // 如果有背景设置，用背景容器包裹模块内容
        if (hasSectionBg) {
          const sectionBgMargin = 0;
          html += '<div class="section-bg-wrapper" style="margin: 0 !important; width: 100% !important; position: relative; overflow: hidden; border-radius: 0;">';
          html += sectionBgHtml;
          html += '<div class="section-bg-content" style="position: relative; z-index: 1;">';
          html += sectionContentHtml;
          html += '</div>';
          html += '</div>';
        } else {
          html += sectionContentHtml;
        }
      });
      
      container.innerHTML = html;
      
      // 初始化所有组件
      this.initAllComponents(container);
    },

    initAllComponents(container) {
      // 初始化tabs
      this.config.sections.forEach((section, index) => {
        if (section.type === 'tabs') {
          const tabsId = 'tabs_section_' + index;
          this.initTabs(tabsId);
        }
      });
      
      // 初始化所有轮播图
      this.initAllCarousels();
      
      // 处理视频封面
      this.setupVideoCovers();
    },
    
    initAllCarousels() {
      const carouselEls = document.querySelectorAll('.carousel');
      carouselEls.forEach((el) => {
        if (el.id && !el.dataset.initialized) {
          this.tryInitCarousel(el.id);
        }
      });
    },
    
    tryInitCarousel(carouselId) {
      const el = document.getElementById(carouselId);
      if (!el) return;
      if (el.dataset.initialized) return;
      
      // 如果轮播图不可见，标记为待处理并延迟重试
      if (el.offsetWidth === 0) {
        el.dataset.carouselPending = 'true';
        const retry = () => {
          setTimeout(() => {
            el.dataset.carouselPending = '';
            if (el.offsetWidth === 0) {
              // 仍然不可见，继续等待
              retry();
            } else {
              this.initCarousel(carouselId);
              el.dataset.initialized = 'true';
            }
          }, 200);
        };
        retry();
        return;
      }
      
      this.initCarousel(carouselId);
      el.dataset.initialized = 'true';
    },
    
    reinitCarousel(carouselId) {
      const el = document.getElementById(carouselId);
      if (!el) return;
      delete el.dataset.initialized;
      this.tryInitCarousel(carouselId);
    },

    renderIconRowSection(section, contentStyle, borderRadiusStyle) {
      const scale = section.scale || 1.0;
      const maxSize = 64 * scale;
      const labelId = 'icon_row_' + Date.now() + Math.floor(Math.random() * 1000);
      
      let html = '<div id="' + labelId + '" class="icon-row" ' + contentStyle + '>';
      html += '<div class="icon-row-container">';
      
      if (section.icons && section.icons.length > 0) {
        section.icons.forEach((icon) => {
          const jumpUrl = this.getAbsoluteUrl(icon.jump);
          html += '<div class="icon-row-item"' + (jumpUrl ? ' data-jump="' + jumpUrl + '"' : '') + '>';
          html += '<img class="clickable-resource" data-res-url="' + this.getAbsoluteUrl(icon.src) + '" src="' + this.getAbsoluteUrl(icon.src) + '"  alt="' + (icon.name || '') + '" loading="lazy" style="max-width:' + maxSize + 'px;max-height:' + maxSize + 'px;">';
          html += '<div class="icon-label">' + (icon.name || '') + '</div>';
          html += '</div>';
        });
      }
      
      html += '</div>';
      html += '</div>';
      
      setTimeout(() => {
        const el = document.getElementById(labelId);
        if (el) {
          el.style.setProperty('--icon-max-size', scale + '');
        }
        this.bindIconRowEvents(labelId);
      }, 0);
      
      return html;
    },
    
    bindIconRowEvents(containerId) {
      const container = document.getElementById(containerId);
      if (!container) return;
      
      const items = container.querySelectorAll('.icon-row-item');
      items.forEach(item => {
        item.addEventListener('click', () => {
          const jumpUrl = item.dataset.jump;
          if (!jumpUrl) return;
          
          const isWechat = navigator.userAgent.toLowerCase().includes('micromessenger');
          if (isWechat) {
            try {
              window.location.href = jumpUrl;
            } catch (e) {
              const link = document.createElement('a');
              link.href = jumpUrl;
              link.target = '_blank';
              link.style.display = 'none';
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
            }
          } else {
            window.open(jumpUrl, '_blank');
          }
        });
      });
    },

    renderNoticeCard(section, contentStyle, borderRadiusStyle) {
      let html = '<div ' + contentStyle + ' onclick="DynamicConfig.showNoticePopup()">';
      html += '<div>';
      html += '<div>📢</div>';
      html += '<div>' + (section.title || '公告') + '</div>';
      html += '</div>';
      html += '<div>' + (section.content || '') + '</div>';
      if (section.tag) {
        html += '<div>';
        html += '<span>' + section.tag + '</span>';
        html += '</div>';
      }
      html += '</div>';
      return html;
    },

    renderMdContactSection(section, contentStyle, borderRadiusStyle) {
      const themeStyles = {
        'theme-purple-pink': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'theme-blue-green': 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)',
        'theme-orange-red': 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
        'theme-cyan-blue': 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
        'theme-gold': 'linear-gradient(135deg, #f6d365 0%, #fda085 100%)',
        'theme-dark-purple': 'linear-gradient(135deg, #30cfd0 0%, #330867 100%)',
        'theme-white': 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
        'theme-dark': 'linear-gradient(135deg, #232526 0%, #414345 100%)'
      };

      const bgTheme = section.bgTheme || 'theme-purple-pink';
      const customColor = section.customColor || '#ffffff';
      const alignment = section.alignment || 'left';
      const logoSize = section.logoSize || 80;
      const borderRadius = 0; // 强制为0消除间隙
      const noBorder = section.noBorder || false;
      const customBgImage = section.customBgImage || '';
      const bgScaleMode = section.bgScaleMode || 'cover'; // 'cover' | 'contain' | 'auto' | 'scale-to-fill'
      const topPadding = section.topPadding !== undefined ? section.topPadding : 20;

      let bgColor = bgTheme === 'custom-color' ? customColor : (themeStyles[bgTheme] || themeStyles['theme-purple-pink']);
      let textColor = bgTheme === 'custom-color' ? '#000000' : '#fff';
      let borderColor = bgTheme === 'custom-color' ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.2)';

      let cardStyle = `background: ${bgColor}; border-radius: ${borderRadius}px; padding: 24px; color: ${textColor}; text-align: ${alignment}; position: relative; overflow: hidden;`;
      if (noBorder) {
        cardStyle += ' border: none; box-shadow: none;';
      } else {
        cardStyle += ` border: 1px solid ${borderColor}; box-shadow: 0 8px 32px rgba(0,0,0,0.12);`;
      }

      let html = '<div ' + contentStyle + '>';
      html += '<div class="md-contact-card" style="' + cardStyle + '">';

      if (customBgImage) {
        html += '<div style="position:absolute;top:0;left:0;width:100%;height:100%;background-image:url(\'' + this.getAbsoluteUrl(customBgImage) + '\');background-size:cover;background-position:center;background-repeat:no-repeat;z-index:0;"></div>';
      }

      html += '<div style="position:relative;z-index:1;">';

      const name = section.name || '';
      const title = section.title || '';
      const phone = section.phone || '';
      const company = section.company || '';
      const address = section.address || '';
      const email = section.email || '';

      if (name || title || phone || company || address || email) {
        html += '<div style="position:relative;">';
        html += '<div style="position:relative;z-index:2;padding-top:' + topPadding + 'px;white-space:nowrap;text-align:' + alignment + ';">';
        if (name) {
          html += '<div style="font-size:24px;font-weight:800;margin-bottom:12px;letter-spacing:1px;">' + name + '</div>';
        }
        if (title) {
          html += '<div style="font-size:14px;line-height:1.6;margin-bottom:6px;opacity:0.85;">' + title + '</div>';
        }
        if (phone) {
          html += '<div style="font-size:14px;line-height:1.6;margin-bottom:6px;opacity:0.85;">' + phone + '</div>';
        }
        if (company) {
          html += '<div style="font-size:14px;line-height:1.6;margin-bottom:6px;opacity:0.85;">' + company + '</div>';
        }
        if (address) {
          html += '<div style="font-size:14px;line-height:1.6;margin-bottom:6px;opacity:0.85;">' + address + '</div>';
        }
        if (email) {
          html += '<div style="font-size:14px;line-height:1.6;margin-bottom:6px;opacity:0.85;">' + email + '</div>';
        }
        html += '</div>';
        html += '</div>';
      }

      html += '</div>';
      html += '</div>';
      html += '</div>';
      return html;
    },

    renderImageButtonSection(section, contentStyle) {
      const imageButtonId = 'imageButton_' + Date.now() + Math.floor(Math.random() * 1000);
      let html = '<div ' + contentStyle + '>';
      html += '<div id="' + imageButtonId + '" class="image-button-container" style="position: relative; width: 100%;">';
      html += '<img class="clickable-resource" data-res-url="' + this.getAbsoluteUrl(section.src) + '" src="' + this.getAbsoluteUrl(section.src) + '"  alt="" loading="lazy" style="width: 100%; height: auto; object-fit: contain; display: block;">';
      
      if (section.buttons && section.buttons.length > 0) {
        section.buttons.forEach((button, index) => {
          const position = button.position || 0;
          const span = button.span || '1x1';
          const [spanWidth, spanHeight] = span.split('x').map(s => parseInt(s) || 1);
          
          const gridSize = 32;
          const row = Math.floor(position / gridSize);
          const col = position % gridSize;
          
          const leftPercent = ((col + spanWidth / 2) / gridSize) * 100;
          const topPercent = ((row + spanHeight / 2) / gridSize) * 100;
          const widthPercent = (spanWidth / gridSize) * 100;
          const heightPercent = (spanHeight / gridSize) * 100;
          
          const buttonColor = button.color || '#4299e1';
          const textColor = button.textColor || '#ffffff';
          const borderRadius = button.borderRadius !== undefined ? button.borderRadius : 8;
          const fontSize = button.fontSize !== undefined ? button.fontSize : 14;
          const bgImage = button.bgImage || '';
          
          const text = button.text || '';
          
          let backgroundStyle = '';
          if (bgImage) {
            const imageUrl = this.getAbsoluteUrl(bgImage);
            console.log('[ImageButton] 背景图片URL:', imageUrl);
            console.log('[ImageButton] bgImage原始值:', bgImage);
            console.log('[ImageButton] 按钮颜色:', buttonColor);
            const imgBtnBgSize = button.bgScaleMode ? (button.bgScaleMode === 'cover' ? 'cover' : button.bgScaleMode === 'contain' ? 'contain' : button.bgScaleMode === 'auto' ? 'auto' : '100% 100%') : 'cover';
            backgroundStyle = 'background-color: #ff0000 !important; background-image: url("' + imageUrl + '") !important; background-position: center center !important; background-size: ' + imgBtnBgSize + ' !important; background-repeat: no-repeat !important; ';
          } else if (buttonColor) {
            backgroundStyle = 'background-color: ' + buttonColor + ' !important; background-image: none !important; ';
          } else {
            backgroundStyle = 'background-color: #4299e1 !important; background-image: none !important; ';
          }
          
          console.log('[ImageButton] 按钮 ' + (index + 1) + ':', {
            position: position,
            row: row,
            col: col,
            span: span,
            spanWidth: spanWidth,
            spanHeight: spanHeight,
            leftPercent: leftPercent,
            topPercent: topPercent,
            widthPercent: widthPercent,
            heightPercent: heightPercent,
            fontSize: fontSize,
            bgImage: bgImage
          });
          
          const buttonHtml = '<button class="image-button" data-jump="' + (this.getAbsoluteUrl(button.jump) || '') + '" style="position: absolute !important; left: ' + leftPercent + '% !important; top: ' + topPercent + '% !important; width: ' + widthPercent + '% !important; height: ' + heightPercent + '% !important; transform: translate(-50%, -50%) !important; ' + backgroundStyle + 'color: ' + textColor + ' !important; border: 1px solid rgba(255,255,255,0.5) !important; border-radius: ' + borderRadius + 'px !important; font-size: ' + fontSize + 'px !important; cursor: pointer !important; display: flex !important; align-items: center !important; justify-content: center !important; padding: 2px 4px !important; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; box-sizing: border-box !important; z-index: 9999 !important; min-width: 40px !important; min-height: 40px !important;">' + text + '</button>';
          console.log('[ImageButton] 生成的按钮HTML:', buttonHtml);
          console.log('[ImageButton] 生成按钮HTML:', {
            leftPercent: leftPercent,
            topPercent: topPercent,
            widthPercent: widthPercent,
            heightPercent: heightPercent,
            backgroundStyle: backgroundStyle,
            textColor: textColor,
            borderRadius: borderRadius,
            fontSize: fontSize,
            text: text
          });
          
          if (bgImage) {
            const imageUrl = this.getAbsoluteUrl(bgImage);
            html += '<button class="image-button" ' +
                    'data-jump="' + (this.getAbsoluteUrl(button.jump) || '') + '" ' +
                    'style="position: absolute !important; ' +
                    'left: ' + leftPercent + '% !important; ' +
                    'top: ' + topPercent + '% !important; ' +
                    'width: ' + widthPercent + '% !important; ' +
                    'height: ' + heightPercent + '% !important; ' +
                    'transform: translate(-50%, -50%) !important; ' +
                    'color: ' + textColor + ' !important; ' +
                    'border: none !important; ' +
                    'border-radius: ' + borderRadius + 'px !important; ' +
                    'font-size: ' + fontSize + 'px !important; ' +
                    'cursor: pointer !important; ' +
                    'display: flex !important; ' +
                    'align-items: center !important; ' +
                    'justify-content: center !important; ' +
                    'padding: 2px 4px !important; ' +
                    'white-space: nowrap !important; ' +
                    'overflow: hidden !important; ' +
                    'text-overflow: ellipsis !important; ' +
                    'box-sizing: border-box !important; ' +
                    'z-index: 9999 !important; ' +
                    'min-width: 40px !important; ' +
                    'min-height: 40px !important; ' +
                    'background-color: transparent !important;">';
            html += '<img class="clickable-resource" data-res-url="' + imageUrl + '" src="' + imageUrl + '"  style="position: absolute !important; top: 0 !important; left: 0 !important; width: 100% !important; height: 100% !important; object-fit: cover !important; border-radius: ' + (borderRadius - 1) + 'px !important; z-index: -1 !important;">';
            if (text) {
              html += '<span style="position: relative !important; z-index: 1 !important;">' + text + '</span>';
            }
            html += '</button>';
          } else {
            html += '<button class="image-button" ' +
                    'data-jump="' + (this.getAbsoluteUrl(button.jump) || '') + '" ' +
                    'style="position: absolute !important; ' +
                    'left: ' + leftPercent + '% !important; ' +
                    'top: ' + topPercent + '% !important; ' +
                    'width: ' + widthPercent + '% !important; ' +
                    'height: ' + heightPercent + '% !important; ' +
                    'transform: translate(-50%, -50%) !important; ' +
                    'background-color: transparent !important; ' +
                    'color: ' + textColor + ' !important; ' +
                    'border: none !important; ' +
                    'border-radius: ' + borderRadius + 'px !important; ' +
                    'font-size: ' + fontSize + 'px !important; ' +
                    'cursor: pointer !important; ' +
                    'display: flex !important; ' +
                    'align-items: center !important; ' +
                    'justify-content: center !important; ' +
                    'padding: 2px 4px !important; ' +
                    'white-space: nowrap !important; ' +
                    'overflow: hidden !important; ' +
                    'text-overflow: ellipsis !important; ' +
                    'box-sizing: border-box !important; ' +
                    'z-index: 9999 !important; ' +
                    'min-width: 40px !important; ' +
                    'min-height: 40px !important;">';
            if (text) {
              html += text;
            }
            html += '</button>';
          }
        });
      }
      
      html += '</div>';
      html += '</div>';
      
      setTimeout(() => {
        this.bindImageButtonEvents(imageButtonId);
      }, 100);
      
      return html;
    },

    renderImageGridLinkSection(section, contentStyle) {
      const gridLinkId = 'imageGridLink_' + Date.now() + Math.floor(Math.random() * 1000);
      const gridSize = section.gridSize || 3;
      const padding = section.padding || 10;
      const gap = section.gap || 2;
      const borderRadius = section.borderRadius !== undefined ? section.borderRadius : 0;
      const links = section.links || {};
      
      let html = '<div ' + contentStyle + '>';
      html += '<div id="' + gridLinkId + '" class="image-grid-link-container" style="position: relative; width: 100%; overflow: hidden; border-radius: ' + borderRadius + 'px;">';
      html += '<img class="clickable-resource" data-res-url="' + this.getAbsoluteUrl(section.src) + '" src="' + this.getAbsoluteUrl(section.src) + '"  alt="" loading="lazy" style="width: 100%; height: auto; object-fit: contain; display: block;">';
      
      html += '<div class="image-grid-link-overlay" style="position: absolute; top: ' + padding + 'px; left: ' + padding + 'px; right: ' + padding + 'px; bottom: ' + padding + 'px; display: grid; grid-template-columns: repeat(' + gridSize + ', 1fr); grid-template-rows: repeat(' + gridSize + ', 1fr); gap: ' + gap + 'px;">';
      
      for (let row = 0; row < gridSize; row++) {
        for (let col = 0; col < gridSize; col++) {
          const key = row + '-' + col;
          const linkUrl = links[key] || '';
          if (linkUrl) {
            html += '<div class="image-grid-link-cell" data-link="' + linkUrl + '" style="cursor: pointer; background: transparent; display: flex; align-items: center; justify-content: center;">';
            html += '</div>';
          } else {
            html += '<div class="image-grid-link-cell" style="background: transparent;">';
            html += '</div>';
          }
        }
      }
      
      html += '</div>';
      html += '</div>';
      html += '</div>';
      
      setTimeout(() => {
        this.bindImageGridLinkEvents(gridLinkId);
      }, 100);
      
      return html;
    },

    bindImageGridLinkEvents(containerId) {
      const container = document.getElementById(containerId);
      if (!container) return;
      
      const cells = container.querySelectorAll('.image-grid-link-cell');
      cells.forEach(cell => {
        cell.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          const jumpUrl = cell.getAttribute('data-link');
          if (!jumpUrl || jumpUrl.trim() === '') return;
          
          const fullUrl = this.getAbsoluteUrl(jumpUrl);
          window.open(fullUrl, '_blank');
        });
        
        cell.addEventListener('touchstart', (e) => {
          cell.style.background = 'rgba(0, 122, 255, 0.15)';
        });
        
        cell.addEventListener('touchend', (e) => {
          cell.style.background = 'transparent';
        });
      });
    },

    bindImageButtonEvents(containerId) {
      const container = document.getElementById(containerId);
      if (!container) return;
      
      const buttons = container.querySelectorAll('.image-button');
      buttons.forEach(button => {
        button.addEventListener('click', (e) => {
          e.stopPropagation();
          const jumpUrl = button.dataset.jump;
          if (!jumpUrl) return;
          
          const isWechat = navigator.userAgent.toLowerCase().includes('micromessenger');
          if (isWechat) {
            try {
              window.location.href = jumpUrl;
            } catch (e) {
              const link = document.createElement('a');
              link.href = jumpUrl;
              link.target = '_blank';
              link.style.display = 'none';
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
            }
          } else {
            window.open(jumpUrl, '_blank');
          }
        });
      });
    },

    renderPDF(url, containerId, maxHeight) {
      const container = document.getElementById(containerId);
      if (!container || typeof pdfjsLib === 'undefined') return;

      // 显示加载状态
      container.innerHTML = '<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: #718096;"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" style="margin-bottom: 12px; animation: spin 1s linear infinite;"><path d="M21 12a9 9 0 11-9-9" stroke="#4a5568" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><span>数据加载中...</span></div>';

      pdfjsLib.getDocument(url).promise.then(pdf => {
        const pagesContainer = document.createElement('div');
        pagesContainer.className = 'pdf-pages-container';
        pagesContainer.style.padding = '16px';
        pagesContainer.style.background = '#f7fafc';

        // 渲染每一页
        const renderPage = (pageNum) => {
          return pdf.getPage(pageNum).then(page => {
            const viewport = page.getViewport({ scale: 1.5 });
            
            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d');
            canvas.width = viewport.width;
            canvas.height = viewport.height;

            const renderContext = {
              canvasContext: context,
              viewport: viewport
            };

            return page.render(renderContext).promise.then(() => {
              const pageContainer = document.createElement('div');
              pageContainer.style.marginBottom = '16px';
              pageContainer.style.background = 'white';
              pageContainer.style.borderRadius = '4px';
              pageContainer.style.boxShadow = '0 1px 3px rgba(0,0,0,0.1)';
              pageContainer.style.overflow = 'hidden';
              
              canvas.style.width = '100%';
              canvas.style.height = 'auto';
              canvas.style.display = 'block';
              
              pageContainer.appendChild(canvas);
              pagesContainer.appendChild(pageContainer);
            });
          });
        };

        // 按顺序渲染所有页面
        let promiseChain = Promise.resolve();
        for (let i = 1; i <= pdf.numPages; i++) {
          promiseChain = promiseChain.then(() => renderPage(i));
        }

        promiseChain.then(() => {
          container.innerHTML = '';
          container.appendChild(pagesContainer);
        }).catch(error => {
          console.error('PDF渲染错误:', error);
          container.innerHTML = '<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: #e53e3e;"><span>数据加载失败</span><span style="font-size: 14px; margin-top: 8px; color: #718096;">点击重试</span></div>';
          container.onclick = () => this.renderPDF(url, containerId, maxHeight);
        });
      }).catch(error => {
        console.error('PDF加载错误:', error);
        container.innerHTML = '<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: #e53e3e;"><span>数据加载失败</span><span style="font-size: 14px; margin-top: 8px; color: #718096;">点击重试</span></div>';
        container.onclick = () => this.renderPDF(url, containerId, maxHeight);
      });
    },

    checkAutoPopupNotice() {
      if (!this.config.sections) return;
      
      const autoPopupNotice = this.config.sections.find(
        section => section.type === 'notice' && section.autoPopup
      );
      
      if (autoPopupNotice) {
        this.currentNotice = autoPopupNotice;
        setTimeout(() => {
          this.showNoticePopup();
        }, 500);
      }
    },

    showNoticePopup() {
      const notice = this.currentNotice || this.config.sections.find(section => section.type === 'notice');
      if (!notice) return;
      
      this.currentNotice = notice;
      
      document.getElementById('noticePopupTitle').textContent = notice.title || '公告';
      document.getElementById('noticePopupBody').textContent = notice.content || '';
      
      const footer = document.getElementById('noticePopupFooter');
      footer.innerHTML = '';
      if (notice.tag) {
        footer.innerHTML = '<span class="notice-tag">' + notice.tag + '</span>';
      }
      
      document.getElementById('noticePopup').classList.add('show');
    },

    hideNoticePopup() {
      document.getElementById('noticePopup').classList.remove('show');
    },

    renderTitleSection(section, logoUrl, spacingStyle) {
      const level = section.level || 1;
      const color = section.color || '';
      const titleLogo = section.logo || logoUrl;
      // 标题颜色：实色 + !important（覆盖 .unified-card-wrapper 的 !important 默认色）
      // 注：CSS 中 .title-text 有 color: #1a1a2e !important，内联 color 必须带 !important 才生效
      const colorStyle = color ? 'style="color: ' + color + ' !important;"' : '';
      // 左侧装饰条颜色（level2 竖条 / level3 竖条 / level1 下方装饰线）
      const decoColor = section.decorationColor || '';
      
      // New style format support
      const backgroundColor = section.backgroundColor || '';
      const borderColor = section.borderColor || '';
      const borderRadius = 0; // 强制为0消除间隙
      const topSpacing = section.topSpacing !== undefined ? section.topSpacing : 0;
      const bottomSpacing = section.bottomSpacing !== undefined ? section.bottomSpacing : 0;
      const titleBorderRadius = section.titleBorderRadius !== undefined ? section.titleBorderRadius : 0;
      const logoBorderRadius = section.logoBorderRadius !== undefined ? section.logoBorderRadius : 8;
      
      // Build inline styles for the section container
      let containerStyles = [];
      
      // Parse the existing styles from spacingStyle
      if (spacingStyle) {
        const styleMatch = spacingStyle.match(/style="([^"]+)"/);
        if (styleMatch && styleMatch[1]) {
          const styles = styleMatch[1].split(';');
          styles.forEach(style => {
            if (style.trim() && !style.trim().startsWith('margin-top') && !style.trim().startsWith('margin-bottom') && !style.trim().startsWith('border-radius') && !style.trim().startsWith('overflow')) {
              containerStyles.push(style.trim());
            }
          });
        }
      }
      
      // Add our new styles
      if (backgroundColor) {
        containerStyles.push('background-color: ' + backgroundColor);
      }
      if (borderColor) {
        containerStyles.push('border: 1px solid ' + borderColor);
      }
      if (topSpacing !== 0) {
        containerStyles.push('margin-top: ' + topSpacing + 'px !important');
      }
      if (bottomSpacing !== 0) {
        containerStyles.push('margin-bottom: ' + bottomSpacing + 'px !important');
      }
      // 应用标题圆角到容器样式（优先于默认 borderRadius）
      if (titleBorderRadius > 0) {
        containerStyles.push('border-radius: ' + titleBorderRadius + 'px !important');
        containerStyles.push('overflow: hidden !important');
      } else if (borderRadius !== 8) {
        containerStyles.push('border-radius: ' + borderRadius + 'px !important');
      }
      const containerStyleAttr = containerStyles.length > 0 ? 'style="' + containerStyles.join(';') + ';"' : '';

      if (level === 1) {
        let html = '<div class="section-title level-1';
        if (section.decorationColor) {
          html += ' has-decoration';
        }
        html += '" ' + containerStyleAttr + '>';
        const titleColorStyle = color ? 'style="color: ' + color + ' !important;"' : '';
        html += '<span class="title-text" ' + titleColorStyle + '>' + (section.title || '') + '</span>';
        if (section.decorationColor) {
          html += '<div class="title-decoration" style="background: ' + section.decorationColor + ' !important;"></div>';
        }
        if (section.subtitle) {
          html += '<div class="title-subtitle">' + section.subtitle + '</div>';
        }
        html += '</div>';
        return html;
      } else if (level === 2) {
        // 二级标题：居左、右侧带 logo；左侧竖条颜色可由 decorationColor 控制
        const height = section.height !== undefined ? section.height : 0;
        let heightStyle = '';
        if (height > 0) {
          heightStyle = 'height: ' + height + 'px; display: flex; align-items: center;';
        }
        let level2ContainerStyle = containerStyleAttr;
        if (heightStyle) {
          if (level2ContainerStyle) {
            level2ContainerStyle = level2ContainerStyle.replace('style="', 'style="' + heightStyle + ' ');
          } else {
            level2ContainerStyle = 'style="' + heightStyle + '"';
          }
        }
        // 左侧竖条内联样式（覆盖 CSS 渐变默认色）
        let html = '<div class="section-title level-2' + (decoColor ? ' has-deco' : '') + '" ' + level2ContainerStyle + '>';
        html += '<span class="title-deco" style="display:block;width:4px;height:100%;position:absolute;left:0;top:0;' + (decoColor ? 'background:' + decoColor + ' !important;' : '') + '"></span>';
        html += '<span class="title-text" ' + colorStyle + '>' + (section.title || '') + '</span>';
        if (titleLogo) {
          const logoStyle = ' style="border-radius: ' + logoBorderRadius + 'px;"';
          html += '<img class="title-logo" class="clickable-resource" data-res-url="' + this.getAbsoluteUrl(titleLogo) + '" src="' + this.getAbsoluteUrl(titleLogo) + '"  alt="Logo"' + logoStyle + '>';
        }
        html += '</div>';
        return html;
      } else if (level === 3) {
        // 三级标题：居左、左侧带 logo；左侧竖条颜色可由 decorationColor 控制
        const decoStyle = decoColor ? ' style="background: ' + decoColor + ' !important;"' : '';
        let html = '<div class="section-title level-3" ' + containerStyleAttr + '>';
        html += '<span class="title-deco"' + decoStyle + '></span>';
        html += '<span class="title-text" ' + colorStyle + '>' + (section.title || '') + '</span>';
        html += '</div>';
        return html;
      }
    },
    
    renderCarouselSection(section, contentStyle, borderRadiusStyle) {
      const carouselId = 'carousel_' + Date.now() + Math.floor(Math.random() * 1000);
      const autoplay = section.autoplay || false;
      const interval = section.interval || 3000;
      const margin = section.margin !== undefined ? section.margin : 0;
      
      const carouselStyle = `style="margin-left: ${margin}px; margin-right: ${margin}px; margin-top: 0; margin-bottom: 0; width: calc(100% - ${margin * 2}px); ${borderRadiusStyle}"`;
      
      let html = '<div class="carousel" id="' + carouselId + '" ' + carouselStyle + '>';
      html += '<div class="carousel-container">';
      
      section.items.forEach((item, index) => {
        html += '<div class="carousel-item" data-jump="' + (this.getAbsoluteUrl(item.jump) || '') + '">';
        html += '<img class="clickable-resource" data-res-url="' + this.getAbsoluteUrl(item.src) + '" src="' + this.getAbsoluteUrl(item.src) + '"  alt="' + (item.title || '') + '" style="border-radius: inherit;">';
        if (item.title) {
          html += '<div class="carousel-item-title">' + item.title + '</div>';
        }
        html += '</div>';
      });
      
      html += '</div>';
      html += '<div class="carousel-indicators"></div>';
      html += '<button class="carousel-prev">&lt;</button>';
      html += '<button class="carousel-next">&gt;</button>';
      html += '</div>';
      
      // 添加轮播图初始化脚本，确保DOM完全渲染
      setTimeout(() => {
        this.initCarousel(carouselId, autoplay, interval);
      }, 100);
      
      return html;
    },
    
    initCarousel(carouselId, autoplay, interval) {
      const carousel = document.getElementById(carouselId);
      if (!carousel) return;

      const container = carousel.querySelector('.carousel-container');
      const items = carousel.querySelectorAll('.carousel-item');
      const indicators = carousel.querySelector('.carousel-indicators');
      const prevBtn = carousel.querySelector('.carousel-prev');
      const nextBtn = carousel.querySelector('.carousel-next');

      if (items.length === 0) return;

      let currentIndex = 0;
      let itemWidth = 0;
      let autoplayInterval = null;

      // 设置默认值
      autoplay = autoplay || false;
      interval = interval || 3000;

      // 确保轮播容器和项目的宽度正确设置
      // 使用多个setTimeout确保DOM已经完全渲染
      const setupCarousel = () => {
        const carouselWidth = carousel.offsetWidth;
        if (carouselWidth === 0) {
          setTimeout(setupCarousel, 50);
          return;
        }

        itemWidth = carouselWidth;
        container.style.width = (itemWidth * items.length) + 'px';
        items.forEach(item => {
          item.style.width = itemWidth + 'px';
          item.style.flexShrink = '0';
        });

        // 处理图片加载后重新计算高度的逻辑
        let imagesLoaded = 0;
        const images = carousel.querySelectorAll('.carousel-item img');
        const totalImages = images.length;

        const updateCarouselHeight = () => {
          const currentItem = items[currentIndex];
          if (!currentItem) return;
          const img = currentItem.querySelector('img');
          if (!img || !img.naturalWidth) return;
          const aspectRatio = img.naturalWidth / img.naturalHeight;
          const height = itemWidth / aspectRatio;
          items.forEach(it => {
            it.style.height = height + 'px';
          });
          container.style.height = height + 'px';
        };

        images.forEach(img => {
          if (img.complete && img.naturalWidth) {
            imagesLoaded++;
            if (imagesLoaded === 1) updateCarouselHeight();
          } else {
            img.addEventListener('load', () => {
              imagesLoaded++;
              if (imagesLoaded === 1) updateCarouselHeight();
            }, { once: true });
          }
        });

        // 清除已存在的指示器
        indicators.innerHTML = '';

        // 创建指示器
        items.forEach((item, index) => {
          const indicator = document.createElement('button');
          indicator.classList.add('carousel-indicator');
          if (index === 0) indicator.classList.add('active');
          indicator.addEventListener('click', () => {
            goToSlide(index);
          });
          indicators.appendChild(indicator);
        });

        // 轮播函数
        const goToSlide = (index) => {
          currentIndex = index;
          container.style.transform = `translateX(-${currentIndex * itemWidth}px)`;

          // 更新高度适应新图片的宽高比
          const currentItem = items[currentIndex];
          if (currentItem) {
            const img = currentItem.querySelector('img');
            if (img && img.naturalWidth) {
              const aspectRatio = img.naturalWidth / img.naturalHeight;
              const height = itemWidth / aspectRatio;
              items.forEach(it => {
                it.style.height = height + 'px';
              });
              container.style.height = height + 'px';
            }
          }

          // 更新指示器状态
          const indicatorButtons = indicators.querySelectorAll('.carousel-indicator');
          indicatorButtons.forEach((btn, i) => {
            if (i === currentIndex) {
              btn.classList.add('active');
            } else {
              btn.classList.remove('active');
            }
          });
        };

        // 上一张
        prevBtn.addEventListener('click', () => {
          currentIndex = (currentIndex - 1 + items.length) % items.length;
          goToSlide(currentIndex);
        });

        // 下一张
        nextBtn.addEventListener('click', () => {
          currentIndex = (currentIndex + 1) % items.length;
          goToSlide(currentIndex);
        });

        // 自动播放
        if (autoplay) {
          autoplayInterval = setInterval(() => {
            currentIndex = (currentIndex + 1) % items.length;
            goToSlide(currentIndex);
          }, interval);
          // 注册interval以便清理
          this._carouselIntervals.push(autoplayInterval);

          // 鼠标悬停时暂停自动播放
          carousel.addEventListener('mouseenter', () => {
            if (autoplayInterval) {
              clearInterval(autoplayInterval);
              autoplayInterval = null;
            }
          });

          carousel.addEventListener('mouseleave', () => {
            if (!autoplayInterval) {
              autoplayInterval = setInterval(() => {
                currentIndex = (currentIndex + 1) % items.length;
                goToSlide(currentIndex);
              }, interval);
              this._carouselIntervals.push(autoplayInterval);
            }
          });
        }

        // 触摸滑动支持
        let touchStartX = 0;
        let isDragging = false;
        let dragOffsetX = 0;

        carousel.addEventListener('touchstart', (e) => {
          touchStartX = e.touches[0].clientX;
          isDragging = true;
          container.style.transition = 'none';
        }, { passive: true });

        carousel.addEventListener('touchmove', (e) => {
          if (!isDragging) return;
          const touchX = e.touches[0].clientX;
          const diffX = touchX - touchStartX;
          dragOffsetX = diffX;
          container.style.transform = `translateX(${-(currentIndex * itemWidth) + dragOffsetX}px)`;
        }, { passive: true });

        carousel.addEventListener('touchend', () => {
          if (!isDragging) return;
          isDragging = false;
          container.style.transition = 'transform 0.3s ease';

          const threshold = itemWidth * 0.2;
          if (Math.abs(dragOffsetX) > threshold) {
            if (dragOffsetX < 0) {
              currentIndex = (currentIndex + 1) % items.length;
            } else {
              currentIndex = (currentIndex - 1 + items.length) % items.length;
            }
          }
          goToSlide(currentIndex);
          dragOffsetX = 0;
        });

        // 鼠标拖拽支持
        let mouseStartX = 0;
        let isMouseDragging = false;
        let mouseDragOffsetX = 0;

        carousel.addEventListener('mousedown', (e) => {
          if (e.button !== 0) return;
          mouseStartX = e.clientX;
          isMouseDragging = true;
          carousel.style.cursor = 'grabbing';
          container.style.transition = 'none';
          e.preventDefault();
        });

        const mouseMoveHandler = (e) => {
          if (!isMouseDragging) return;
          const diffX = e.clientX - mouseStartX;
          mouseDragOffsetX = diffX;
          container.style.transform = `translateX(${-(currentIndex * itemWidth) + mouseDragOffsetX}px)`;
        };
        document.addEventListener('mousemove', mouseMoveHandler);

        const mouseUpHandler = () => {
          if (!isMouseDragging) return;
          isMouseDragging = false;
          carousel.style.cursor = 'grab';
          container.style.transition = 'transform 0.3s ease';

          const threshold = itemWidth * 0.2;
          if (Math.abs(mouseDragOffsetX) > threshold) {
            if (mouseDragOffsetX < 0) {
              currentIndex = (currentIndex + 1) % items.length;
            } else {
              currentIndex = (currentIndex - 1 + items.length) % items.length;
            }
          }
          goToSlide(currentIndex);
          mouseDragOffsetX = 0;
        };
        document.addEventListener('mouseup', mouseUpHandler);

        // 处理跳转
        items.forEach(item => {
          item.addEventListener('click', () => {
            const jumpUrl = item.dataset.jump;
            if (jumpUrl) {
              const isWechat = navigator.userAgent.toLowerCase().includes('micromessenger');
              if (isWechat) {
                try {
                  window.location.href = jumpUrl;
                } catch (e) {
                  const link = document.createElement('a');
                  link.href = jumpUrl;
                  link.target = '_blank';
                  link.style.display = 'none';
                  document.body.appendChild(link);
                  link.click();
                  document.body.removeChild(link);
                }
              } else {
                window.open(jumpUrl, '_blank');
              }
            }
          });
        });

        // 监听窗口大小变化，重新计算宽度
        const resizeHandler = () => {
          const newCarouselWidth = carousel.offsetWidth;
          if (newCarouselWidth === 0) return;
          itemWidth = newCarouselWidth;
          container.style.width = (itemWidth * items.length) + 'px';
          items.forEach(item => {
            item.style.width = itemWidth + 'px';
          });
          // 重新定位到当前幻灯片
          container.style.transform = `translateX(-${currentIndex * itemWidth}px)`;
          // 重新计算高度
          const currentItem = items[currentIndex];
          if (currentItem) {
            const img = currentItem.querySelector('img');
            if (img && img.naturalWidth) {
              const aspectRatio = img.naturalWidth / img.naturalHeight;
              const height = itemWidth / aspectRatio;
              items.forEach(it => {
                it.style.height = height + 'px';
              });
              container.style.height = height + 'px';
            }
          }
        };
        window.addEventListener('resize', resizeHandler);
        // 注册resize handler以便清理
        this._carouselResizeHandlers.push(resizeHandler);
      };

      // 启动轮播图设置
      setTimeout(setupCarousel, 100);
    },
    
    renderTabsSection(section, index, contentStyle, borderRadiusStyle) {
      const tabsId = 'tabs_section_' + index;
      const tabGap = section.tabGap !== undefined ? section.tabGap : 8;
      let html = '<div id="' + tabsId + '" ' + contentStyle + '>';
      html += '<div>';
      html += '<div class="tabs-header" data-count="' + section.tabs.length + '" style="gap: ' + tabGap + 'px;">';
      
      section.tabs.forEach((tab, tabIndex) => {
        html += '<div class="tab-item' + (tabIndex === 0 ? ' active' : '') + '" data-index="' + tabIndex + '">';
        html += tab.title;
        html += '</div>';
      });
      
      html += '</div>';
      html += '<div class="tabs-content">';
      
      section.tabs.forEach((tab, tabIndex) => {
        html += '<div class="tab-pane' + (tabIndex === 0 ? ' active' : '') + '" data-index="' + tabIndex + '">';
        
        // 渲染tab内的区块
        tab.sections.forEach((tabSection) => {
          const tabMargin = 0;
          const tabBorderRadius = 0;
          const tabContainerStyle = `style="margin: 0 !important; padding: 0 !important; border-radius: 0 !important;"`;
          
          switch (tabSection.type) {
            case 'title':
              // 为标签页内的标题组件创建样式
              const tabTitleMargin = 0;
              const tabTitleStyle = `style="margin: 0 !important; padding: 0 !important; width: 100% !important; border-radius: 0 !important;"`;
              html += this.renderTitleSection(tabSection, '', tabTitleStyle);
              break;
            case 'image':
              html += '<div ' + tabContainerStyle + ' data-jump="' + (this.getAbsoluteUrl(tabSection.jump) || '') + '">' +
                      '<img class="clickable-resource" data-res-url="' + this.getAbsoluteUrl(tabSection.src) + '" src="' + this.getAbsoluteUrl(tabSection.src) + '"  alt="" loading="lazy" style="width: 100%; height: auto; max-height: 100%; object-fit: contain; border-radius: inherit;">' +
                      '</div>';
              break;
            case 'video':
              const videoId = 'video_' + Date.now() + Math.floor(Math.random() * 1000);
              html += '<div ' + tabContainerStyle + '>' +
                      '<video id="' + videoId + '" src="' + this.getAbsoluteUrl(tabSection.src) + '" poster="' + (this.getAbsoluteUrl(tabSection.poster) || '') + '" controls playsinline webkit-playsinline preload="none" style="width: 100%; height: auto; object-fit: contain; border-radius: inherit;"></video>' +
                      '</div>';
              break;
            case 'grid':
              const tabGridPadding = tabSection.padding !== undefined ? tabSection.padding : 0;
              const tabGridGap = tabSection.gap !== undefined ? tabSection.gap : 4;
              const tabGridBorderRadius = tabSection.borderRadius !== undefined ? tabSection.borderRadius : 0;
              html += '<div ' + tabContainerStyle + '>';
              html += '<div class="image-grid" style="--grid-padding: ' + tabGridPadding + 'px; --grid-gap: ' + tabGridGap + 'px; border-radius: ' + tabGridBorderRadius + 'px; overflow: hidden;">';
              tabSection.images.forEach((img) => {
                html += '<div class="image-grid-item" data-jump="' + (this.getAbsoluteUrl(img.jump) || '') + '">' +
                        '<img class="clickable-resource" data-res-url="' + this.getAbsoluteUrl(img.src) + '" src="' + this.getAbsoluteUrl(img.src) + '"  alt="" loading="lazy">' +
                        '</div>';
              });
              html += '</div>';
              html += '</div>';
              break;
            case 'carousel':
              const carouselTabId = 'carousel_tab_' + Date.now() + Math.floor(Math.random() * 1000);
              html += '<div class="carousel" id="' + carouselTabId + '" ' + tabContainerStyle + '>';
              html += '<div class="carousel-container">';
              if (tabSection.items && tabSection.items.length > 0) {
                tabSection.items.forEach((item) => {
                  html += '<div class="carousel-item" data-jump="' + (this.getAbsoluteUrl(item.jump) || '') + '">';
                  html += '<img class="clickable-resource" data-res-url="' + this.getAbsoluteUrl(item.src) + '" src="' + this.getAbsoluteUrl(item.src) + '"  alt="' + (item.title || '') + '" loading="lazy" style="border-radius: inherit;">';
                  html += '</div>';
                });
              }
              html += '</div>';
              html += '</div>';
              break;
            case 'iconRow':
              html += this.renderIconRowSection(tabSection, '', '');
              break;
            case 'imageButton':
              html += this.renderImageButtonSection(tabSection, tabContainerStyle);
              break;
            case 'imageGridLink':
              html += this.renderImageGridLinkSection(tabSection, tabContainerStyle);
              break;
            case 'pdf':
              const pdfTabHeight = tabSection.height || 600;
              const pdfTabId = 'pdf-tab-' + Date.now() + Math.floor(Math.random() * 1000);
              html += '<div class="pdf-section" style="width: 100%;">' +
                      '<div class="pdf-viewer" id="' + pdfTabId + '" style="width: 100%; background: #f7fafc; border-radius: 8px; overflow: hidden;"></div>' +
                      '</div>';
              setTimeout(() => {
                this.renderPDF(this.getAbsoluteUrl(tabSection.src), pdfTabId, pdfTabHeight);
              }, 100);
              break;
          }
        });
        
        html += '</div>';
      });
      
      html += '</div>';
      html += '</div>';
      
      return html;
    },
    
    initTabs(tabsId) {
      const self = this;
      const tabs = document.getElementById(tabsId);
      if (!tabs) return;
      
      const tabItems = Array.from(tabs.querySelectorAll('.tab-item'));
      const tabPanes = Array.from(tabs.querySelectorAll('.tab-pane'));
      
      // 立即初始化第一个可见tab内的轮播图和视频封面
      const activePane = tabs.querySelector('.tab-pane.active');
      if (activePane) {
        activePane.querySelectorAll('.carousel').forEach((el) => {
          if (el.id && !el.dataset.initialized && !el.dataset.carouselPending) {
            self.tryInitCarousel(el.id);
          }
        });
        // 处理当前可见tab内的视频
        activePane.querySelectorAll('video').forEach((video) => {
          if (!video.poster) {
            self.generateVideoThumbnailForVideo(video);
          }
        });
      }
      
      // 监听 tab-pane 的 class 变化，在可见时初始化内部轮播图和视频
      const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          if (mutation.attributeName === 'class') {
            const target = mutation.target;
            if (target.classList.contains('active')) {
              target.querySelectorAll('.carousel').forEach((el) => {
                if (el.id && !el.dataset.initialized && !el.dataset.carouselPending) {
                  self.tryInitCarousel(el.id);
                }
              });
              // 处理当前激活tab内的视频
              target.querySelectorAll('video').forEach((video) => {
                if (!video.poster) {
                  self.generateVideoThumbnailForVideo(video);
                }
              });
            }
          }
        });
      });
      
      tabPanes.forEach((pane) => {
        observer.observe(pane, { attributes: true });
      });
      
      tabItems.forEach((item, index) => {
        item.addEventListener('click', () => {
          tabItems.forEach(i => i.classList.remove('active'));
          tabPanes.forEach(p => p.classList.remove('active'));
          item.classList.add('active');
          if (tabPanes[index]) {
            tabPanes[index].classList.add('active');
          }
        });
      });
    },
    
    initVisibleCarousels(container) {
      if (!container) return;
      const carouselEls = container.querySelectorAll ? container.querySelectorAll('.carousel') : [];
      carouselEls.forEach((el) => {
        if (el.id && !el.dataset.initialized) {
          this.initCarousel(el.id);
          el.dataset.initialized = 'true';
        }
      });
    },
    
    setupVideoCovers() {
      console.log('开始设置视频封面...');
      const videos = document.querySelectorAll('video');
      console.log('找到视频数量:', videos.length);
      
      videos.forEach((video, index) => {
        console.log(`处理视频 ${index + 1}:`, video.src);
        // 如果已经设置了poster，跳过
        if (video.poster && video.poster.length > 10) {
          console.log('视频已有poster，跳过');
          return;
        }
        
        // 不强制调用video.load()避免触发网络请求
        // 仅监听元数据加载事件来生成封面
        let setCoverAttempted = false;
        
        const tryGenerateCover = () => {
          if (setCoverAttempted) return;
          setCoverAttempted = true;
          try {
            this.generateVideoThumbnail(video);
          } catch (e) {
            console.log('Canvas生成失败，保留默认样式');
          }
        };
        
        video.addEventListener('loadedmetadata', () => {
          setTimeout(tryGenerateCover, 200);
        }, { once: true });
        
        video.addEventListener('loadeddata', tryGenerateCover, { once: true });
        
        // 超时兜底
        setTimeout(() => {
          if (!setCoverAttempted) tryGenerateCover();
        }, 3000);
      });
    },
    
    generateVideoThumbnailForVideo(video) {
      // 保留接口兼容，实际调用setupVideoCovers
      this.setupVideoCovers();
    },
    
    generateVideoThumbnail(video) {
      if (video.poster && video.poster.length > 10) {
        console.log('视频已有poster，跳过生成');
        return;
      }
      
      console.log('开始生成视频缩略图...');
      try {
        // 首先检查视频是否真的准备好
        if (!video.videoWidth || video.videoWidth === 0) {
          console.log('视频尺寸未就绪，无法生成封面');
          return;
        }
        
        // 创建一个canvas元素
        const canvas = document.createElement('canvas');
        const width = video.videoWidth;
        const height = video.videoHeight;
        canvas.width = width;
        canvas.height = height;
        
        console.log('canvas尺寸:', width, 'x', height);
        
        // 绘制视频的当前帧
        const ctx = canvas.getContext('2d');
        let drawSuccess = false;
        
        try {
          ctx.drawImage(video, 0, 0, width, height);
          drawSuccess = true;
          console.log('成功绘制视频帧到canvas');
        } catch (drawError) {
          console.error('绘制视频帧失败:', drawError);
          // 在微信环境中，尝试使用更简单的方法
          // 我们可能无法通过canvas获取，这时候CSS fallback会起作用
          return;
        }
        
        // 只有在绘制成功时才继续
        if (!drawSuccess) {
          return;
        }
        
        // 将canvas转换为base64图片
        let thumbnailUrl;
        try {
          thumbnailUrl = canvas.toDataURL('image/jpeg', 0.85);
          console.log('成功生成base64图片，长度:', thumbnailUrl.length);
        } catch (toDataUrlError) {
          console.error('toDataURL失败:', toDataUrlError);
          return;
        }
        
        // 设置视频的poster属性
        if (thumbnailUrl && thumbnailUrl.length > 100) {
          video.poster = thumbnailUrl;
          console.log('成功设置视频poster');
        }
        
      } catch (e) {
        console.error('生成视频封面时出错:', e);
      }
    },

    async initWechatShare() {
      console.log('开始初始化微信分享...');
      
      // 优先从名片信息组件获取数据
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      let info = contactSection || this.config.basicInfo;
      
      // 使用当前页面的分享标题、描述和图标
      let shareTitle = '';
      let shareDesc = '';
      let shareIcon = '';
      
      if (this.config.currentPage) {
        shareTitle = this.config.currentPage.share_title || '';
        shareDesc = this.config.currentPage.share_desc || '';
        shareIcon = this.config.currentPage.share_icon || '';
      }
      
      // 如果没有配置分享信息，则使用名片信息
      if (!shareTitle) {
        shareTitle = (info.name || '微信名片') + '的微信名片';
      }
      
      if (!shareDesc) {
        shareDesc = (info.title || '') + (info.phone ? ' | ' + info.phone : '');
      }
      
      // 确保分享图片是完整的URL
      let finalShareIcon = shareIcon;
      if (finalShareIcon && !finalShareIcon.startsWith('http')) {
        if (finalShareIcon.startsWith('/')) {
          finalShareIcon = this.serverUrl + finalShareIcon;
        } else {
          finalShareIcon = this.serverUrl + '/' + finalShareIcon;
        }
      }
      if (!finalShareIcon) {
        finalShareIcon = this.serverUrl + '/uploads/20260415_063127_e659038a.png';
      }
      
      console.log('分享设置:', {
        title: shareTitle,
        desc: shareDesc,
        link: window.location.href,
        imgUrl: finalShareIcon
      });
      
      console.log('是否微信环境:', WechatJSSDK.isWechat());
      
      if (!WechatJSSDK.isWechat()) {
        console.log('非微信环境，跳过JSSDK配置');
        return;
      }
      
      console.log('开始获取微信签名...');
      
      try {
        const signUrl = this.serverUrl + '/api/wechat-sign?url=' + encodeURIComponent(window.location.href.split('#')[0]);
        console.log('签名请求URL:', signUrl);
        
        const response = await this.fetchWithTimeout(signUrl, {}, 5000);
        const signData = await response.json();
        
        console.log('微信签名数据:', signData);
        
        if (signData.appId) {
          console.log('开始配置微信JSSDK...');
          WechatJSSDK.config({
            appId: signData.appId,
            timestamp: signData.timestamp,
            nonceStr: signData.nonceStr,
            signature: signData.signature,
            onReady: () => {
              console.log('微信JSSDK ready，设置分享数据');
              WechatJSSDK.setShareData({
                title: shareTitle,
                desc: shareDesc,
                link: window.location.href,
                imgUrl: finalShareIcon
              });
            },
            onError: (res) => {
              console.error('微信JSSDK配置错误:', res);
              // 不显示错误提示，保持用户体验
            }
          });
        } else {
          console.error('签名数据中没有appId');
        }
      } catch (e) {
        console.error('获取微信签名失败:', e);
        // 不显示错误提示，保持用户体验
      }
    },

    bindEvents() {
      const btnCopy = document.getElementById('btnCopy');
      if (btnCopy) {
        btnCopy.addEventListener('click', () => this.handleCopy());
      }
      
      const btnCall = document.getElementById('btnCall');
      if (btnCall) {
        btnCall.addEventListener('click', () => this.handleCall());
      }
      
      // 公告弹窗事件
      const closeNoticeBtn = document.getElementById('closeNoticePopup');
      if (closeNoticeBtn) {
        closeNoticeBtn.addEventListener('click', () => this.hideNoticePopup());
      }
      
      const noticePopup = document.getElementById('noticePopup');
      if (noticePopup) {
        noticePopup.addEventListener('click', (e) => {
          if (e.target.id === 'noticePopup') this.hideNoticePopup();
        });
      }
      
      const cancelCall = document.getElementById('cancelCall');
      if (cancelCall) {
        cancelCall.addEventListener('click', () => this.hideCallConfirm());
      }
      
      const confirmCall = document.getElementById('confirmCall');
      if (confirmCall) {
        confirmCall.addEventListener('click', () => this.doCall());
      }
      
      const callConfirm = document.getElementById('callConfirm');
      if (callConfirm) {
        callConfirm.addEventListener('click', (e) => {
          if (e.target.id === 'callConfirm') this.hideCallConfirm();
        });
      }
      
      const contentSections = document.getElementById('contentSections');
      if (contentSections) {
        contentSections.addEventListener('click', (e) => {
          const card = e.target.closest('.image-card, .image-grid-item, [data-jump]:not(.image-button)');
          if (card && card.dataset.jump) {
            const jumpUrl = card.dataset.jump;
            
            // 检测是否在微信环境中
            const isWechat = navigator.userAgent.toLowerCase().includes('micromessenger');
            
            if (isWechat) {
              // 在微信环境中，尝试使用不同的跳转方式
              try {
                // 方法1：直接设置location.href
                window.location.href = jumpUrl;
              } catch (e) {
                // 方法2：创建一个a标签并点击
                const link = document.createElement('a');
                link.href = jumpUrl;
                link.target = '_blank';
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
              }
            } else {
              // 在非微信环境中，使用window.open
              window.open(jumpUrl, '_blank');
            }
          }
          
          // 处理图片放大功能
          const zoomableContainer = e.target.closest('[data-zoomable="true"]');
          if (zoomableContainer) {
            const img = zoomableContainer.querySelector('img');
            if (img) {
              this.zoomImage(img.src);
            }
          }
        });
      }
    },
    
    zoomImage(src) {
      const overlay = document.createElement('div');
      overlay.className = 'image-zoom-overlay';
      overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
        cursor: zoom-out;
        animation: fadeIn 0.2s ease;
        overflow: hidden;
      `;
      
      const imgContainer = document.createElement('div');
      imgContainer.style.cssText = `
        position: relative;
        touch-action: none;
        user-select: none;
      `;
      
      const img = document.createElement('img');
      img.src = src;
      img.style.cssText = `
        max-width: 90vw;
        max-height: 90vh;
        object-fit: contain;
        animation: zoomIn 0.3s ease;
        touch-action: none;
      `;
      
      const closeBtn = document.createElement('button');
      closeBtn.innerHTML = '×';
      closeBtn.style.cssText = `
        position: absolute;
        top: 20px;
        right: 20px;
        width: 48px;
        height: 48px;
        border: none;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.2);
        color: white;
        font-size: 32px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.2s;
        z-index: 10;
      `;
      closeBtn.onmouseover = () => closeBtn.style.background = 'rgba(255, 255, 255, 0.3)';
      closeBtn.onmouseout = () => closeBtn.style.background = 'rgba(255, 255, 255, 0.2)';
      
      const close = () => {
        overlay.style.animation = 'fadeOut 0.2s ease';
        setTimeout(() => {
          document.body.removeChild(overlay);
        }, 200);
      };
      
      overlay.addEventListener('click', close);
      closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        close();
      });
      
      // 缩放和拖动功能
      let scale = 1;
      let posX = 0;
      let posY = 0;
      let isDragging = false;
      let lastTouchX = 0;
      let lastTouchY = 0;
      let lastDistance = 0;
      let lastTouchCenterX = 0;
      let lastTouchCenterY = 0;
      
      const updateTransform = () => {
        imgContainer.style.transform = `translate(${posX}px, ${posY}px) scale(${scale})`;
      };
      
      // 双击缩放
      img.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        if (scale > 1) {
          scale = 1;
          posX = 0;
          posY = 0;
        } else {
          scale = 2;
        }
        updateTransform();
      });
      
      // 鼠标滚轮缩放
      img.addEventListener('wheel', (e) => {
        e.stopPropagation();
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.1 : 0.1;
        scale = Math.max(0.5, Math.min(5, scale + delta));
        updateTransform();
      });
      
      // 触摸开始
      let touchStartDist = 0;
      let touchStartScale = 1;
      
      img.addEventListener('touchstart', (e) => {
        if (e.touches.length === 2) {
          // 双指缩放
          const touch1 = e.touches[0];
          const touch2 = e.touches[1];
          touchStartDist = Math.hypot(touch2.clientX - touch1.clientX, touch2.clientY - touch1.clientY);
          touchStartScale = scale;
        } else if (e.touches.length === 1) {
          // 单指拖动
          isDragging = true;
          lastTouchX = e.touches[0].clientX - posX;
          lastTouchY = e.touches[0].clientY - posY;
        }
      }, { passive: true });
      
      // 触摸移动
      img.addEventListener('touchmove', (e) => {
        if (e.touches.length === 2) {
          // 双指缩放
          const touch1 = e.touches[0];
          const touch2 = e.touches[1];
          const dist = Math.hypot(touch2.clientX - touch1.clientX, touch2.clientY - touch1.clientY);
          const delta = dist / touchStartDist;
          scale = Math.max(0.5, Math.min(5, touchStartScale * delta));
          updateTransform();
        } else if (e.touches.length === 1 && isDragging && scale > 1) {
          // 单指拖动（只有放大后才能拖动）
          posX = e.touches[0].clientX - lastTouchX;
          posY = e.touches[0].clientY - lastTouchY;
          updateTransform();
        }
      }, { passive: false });
      
      // 触摸结束
      img.addEventListener('touchend', () => {
        isDragging = false;
      }, { passive: true });
      
      // 鼠标拖动
      img.addEventListener('mousedown', (e) => {
        if (scale > 1) {
          isDragging = true;
          lastTouchX = e.clientX - posX;
          lastTouchY = e.clientY - posY;
          e.preventDefault();
        }
      });
      
      document.addEventListener('mousemove', (e) => {
        if (isDragging && scale > 1) {
          posX = e.clientX - lastTouchX;
          posY = e.clientY - lastTouchY;
          updateTransform();
        }
      });
      
      document.addEventListener('mouseup', () => {
        isDragging = false;
      });
      
      imgContainer.appendChild(img);
      overlay.appendChild(imgContainer);
      overlay.appendChild(closeBtn);
      document.body.appendChild(overlay);
      
      const style = document.createElement('style');
      style.textContent = `
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes fadeOut {
          from { opacity: 1; }
          to { opacity: 0; }
        }
        @keyframes zoomIn {
          from { transform: scale(0.9); opacity: 0; }
          to { transform: scale(1); opacity: 1; }
        }
      `;
      document.head.appendChild(style);
    },



    handleCopy() {
      console.log('点击了复制信息按钮');
      if (navigator.vibrate) navigator.vibrate(50);
      
      // 优先使用名片信息组件的数据
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      const info = contactSection || this.config.basicInfo;
      
      // 构建要复制的文本
      let copyText = '';
      
      if (info.name) {
        copyText += `姓名：${info.name}\n`;
      }
      if (info.phone) {
        copyText += `电话：${info.phone}\n`;
      }
      if (info.title2 || info.title) {
        copyText += `职位：${info.title2 || info.title}\n`;
      }
      if (info.email) {
        copyText += `邮箱：${info.email}\n`;
      }
      if (info.company) {
        copyText += `公司：${info.company}\n`;
      }
      if (info.address) {
        copyText += `地址：${info.address}\n`;
      }
      
      // 尝试复制到剪贴板
      this.copyToClipboard(copyText);
    },

    copyToClipboard(text, successMsg) {
      const msg = successMsg || '信息已复制到剪贴板';
      if (navigator.clipboard && navigator.clipboard.writeText) {
        // 使用现代的Clipboard API
        navigator.clipboard.writeText(text).then(() => {
          this.showToast(msg, 'success');
        }).catch(() => {
          this.fallbackCopy(text, msg);
        });
      } else {
        // 使用传统的方法作为后备
        this.fallbackCopy(text, msg);
      }
    },

    fallbackCopy(text, successMsg) {
      const msg = successMsg || '信息已复制到剪贴板';
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-9999px';
      textArea.style.top = '-9999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      try {
        document.execCommand('copy');
        this.showToast(msg, 'success');
      } catch (e) {
        this.showToast('复制失败，请手动复制', 'error');
      }
      
      document.body.removeChild(textArea);
    },

    handleCall() {
      if (navigator.vibrate) navigator.vibrate(50);
      // 直接拨号，不弹确认框
      this.doCall();
    },

    showCallConfirm() {
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      const phone = contactSection ? (contactSection.mobilePhone || contactSection.phone) : this.config.basicInfo.phone;
      document.getElementById('confirmPhone').textContent = phone;
      document.getElementById('callConfirm').classList.add('show');
    },

    hideCallConfirm() {
      document.getElementById('callConfirm').classList.remove('show');
    },

    // 一键拨号（微信内 tel: 链接可直接调起拨号面板）
    doCall() {
      this.hideCallConfirm();
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      const info = { ...(this.config.basicInfo || {}), ...(contactSection || {}) };
      const phone = info.mobilePhone || info.phone || '';
      if (!phone) {
        this.showToast('暂未设置手机号码', 'error');
        return;
      }
      window.location.href = 'tel:' + phone;
    },

    showToast(message, type, duration) {
      const toast = document.getElementById('toast');
      toast.textContent = message;
      toast.className = 'toast show' + (type ? ' ' + type : '');
      setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.className = 'toast', 300);
      }, duration || 2000);
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => DynamicConfig.init());
  } else {
    DynamicConfig.init();
  }

  window.DynamicConfig = DynamicConfig;
})();
