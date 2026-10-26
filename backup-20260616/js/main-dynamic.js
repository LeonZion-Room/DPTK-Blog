(function() {
  'use strict';

  const DynamicConfig = {
    config: null,
    serverUrl: '',
    currentNotice: null,

    // 辅助函数：将相对URL或本地IP URL转换为使用serverUrl的绝对URL
    getAbsoluteUrl(url) {
      if (!url) return url;
      if (url.startsWith('http')) {
        // 检查是否是本地IP URL，如果是则替换为serverUrl
        if (url.includes('172.168.') || url.includes('192.168.') || url.includes('127.0.0.1') || url.includes('localhost')) {
          // 提取路径部分
          const path = url.replace(/^https?:\/\/[^\/]+/, '');
          return this.serverUrl + path;
        }
        return url;
      }
      // 非http开头的URL，检查是否是相对路径
      if (url.startsWith('/')) {
        // 绝对路径（以/开头）
        return this.serverUrl + url;
      } else {
        // 相对路径，添加uploads前缀
        return this.serverUrl + '/uploads/' + url;
      }
    },

    async init() {
      await this.loadConfig();
      this.setMobileGap();
      this.renderBasicInfo();
      this.renderSections();
      await this.initWechatShare();
      this.bindEvents();
      this.checkAutoPopupNotice();
      // 等待DOM完全渲染后再处理视频
      setTimeout(() => {
        this.setupVideoCovers();
      }, 500);
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
        
        const url = pageId ? 
          defaultServerUrl + '/api/card-config?page=' + pageId : 
          defaultServerUrl + '/api/card-config';
        
        const response = await fetch(url);
        if (response.ok) {
          this.config = await response.json();
          console.log('Loaded config:', this.config);
          // 使用currentPage的sections
          if (this.config.currentPage) {
            this.config.sections = this.config.currentPage.sections;
            console.log('Sections from currentPage:', this.config.sections);
          }
          // 设置serverUrl为后端返回的currentDomain
          if (this.config.currentDomain) {
            this.serverUrl = this.config.currentDomain;
          } else {
            this.serverUrl = defaultServerUrl;
          }
        } else {
          this.config = typeof CardConfig !== 'undefined' ? CardConfig : this.getDefaultConfig();
          this.serverUrl = defaultServerUrl;
        }
      } catch (e) {
        this.config = typeof CardConfig !== 'undefined' ? CardConfig : this.getDefaultConfig();
        this.serverUrl = window.location.origin;
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
      // 移除之前的主题类
      document.body.className = document.body.className.replace(/bg-theme-\S+/g, '').trim();
      document.body.className = document.body.className.replace(/content-theme-\S+/g, '').trim();
      
      // 检查是否有名片信息组件
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      
      // 如果页面没有contact组件，直接隐藏个人信息区域
      if (!contactSection) {
        const infoCardWrapper = document.querySelector('.info-card-wrapper');
        if (infoCardWrapper) {
          infoCardWrapper.style.display = 'none';
        }
        return;
      }
      
      // 优先使用 basicInfo 配置，其次使用 contactSection
      const basicInfo = this.config.basicInfo || {};
      const info = contactSection || basicInfo;
      
      if (info && (contactSection || (basicInfo.name || basicInfo.phone))) {
        // 获取info-card容器
        const infoCard = document.querySelector('.info-card');
        
        // 清除之前的自定义背景
        const existingBg = infoCard?.querySelector('.custom-card-bg');
        if (existingBg) existingBg.remove();
        
        // 重置背景样式
        if (infoCard) {
          infoCard.style.background = '';
          infoCard.style.backgroundImage = '';
          infoCard.style.backgroundSize = '';
          infoCard.style.backgroundPosition = '';
          infoCard.style.backgroundRepeat = '';
        }
        
        // 应用背景设置到info-card容器
        // 优先使用页面级别的配置（currentPage），其次使用basicInfo，最后使用contactSection
        const currentPage = this.getCurrentPage();
        const cardBgTheme = currentPage?.card_bg_theme || basicInfo.bgTheme || info.bgTheme || info.theme;
        const cardCustomBgImage = currentPage?.card_custom_bg_image || basicInfo.customBgImage || info.customBgImage;
        
        // 检查是否使用自定义背景图片
        if (cardCustomBgImage) {
          // 创建自定义背景图片元素
          const bgImage = document.createElement('div');
          bgImage.className = 'custom-card-bg';
          bgImage.style.cssText = `
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-image: url('${this.getAbsoluteUrl(cardCustomBgImage)}');
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            border-radius: inherit;
            z-index: 0;
          `;
          
          // 确保info-card有相对定位
          if (infoCard) {
            infoCard.style.position = 'relative';
            infoCard.style.overflow = 'hidden';
            infoCard.appendChild(bgImage);
          }
        } else if (cardBgTheme) {
          // 应用主题背景到info-card
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
        
        // 更新基本信息
        const nameEl = document.getElementById('name');
        const phoneEl = document.getElementById('phone');
        const titleEl = document.getElementById('title');
        const title2El = document.getElementById('title2');
        const emailEl = document.getElementById('email');
        const logoEl = document.getElementById('logo');
        
        if (nameEl) nameEl.textContent = info.name || '';
        if (phoneEl) phoneEl.textContent = info.phone || '';
        if (titleEl) titleEl.textContent = info.title || '';
        if (title2El) title2El.textContent = info.title2 || '';
        if (emailEl) emailEl.textContent = info.email ? '邮箱：' + info.email : '';
        
        if (logoEl && info.logo) {
          logoEl.src = this.getAbsoluteUrl(info.logo);
        }
        
        // 设置名片文本对齐方式
        if (infoCard) {
          // 移除之前的对齐类
          infoCard.className = infoCard.className.replace(/align-\S+/g, '').trim();
          // 添加新的对齐类
          const alignment = info.alignment || 'center';
          infoCard.classList.add('align-' + alignment);
          
          // 处理无边框选项
          if (info.noBorder || basicInfo.noBorder) {
            infoCard.style.border = 'none';
            infoCard.style.boxShadow = 'none';
            infoCard.style.borderRadius = '0';
          }
        }
        
        // 应用顶部内边距到 info-content
        const infoContent = document.querySelector('.info-content');
        const topPadding = info.topPadding !== undefined ? info.topPadding : 45;
        if (infoContent) {
          infoContent.style.marginTop = topPadding + 'px';
        }
        
        // 设置Logo大小
        const logoContainer = document.querySelector('.logo-container');
        if (logoContainer && (info.logoSize || basicInfo.logoSize)) {
          logoContainer.style.setProperty('--logo-size', (info.logoSize || basicInfo.logoSize) + 'px');
        }
        
        // 设置Logo圆角
        if (logoEl && (basicInfo.borderRadius !== undefined)) {
          logoEl.style.borderRadius = basicInfo.borderRadius + 'px';
        }
        
        // 处理第一个按钮的链接设置
        const btnCopy = document.getElementById('btnCopy');
        const btnLink = document.getElementById('btnLink');
        const btnCall = document.getElementById('btnCall');
        
        // 应用自定义按钮颜色
        const btnColor = info.btnColor || basicInfo.btnColor;
        const btnTextColor = info.btnTextColor || basicInfo.btnTextColor;
        const btnOpacity = info.btnOpacity !== undefined ? info.btnOpacity : (basicInfo.btnOpacity !== undefined ? basicInfo.btnOpacity : 1.0);
        const btnFontSize = info.btnFontSize || basicInfo.btnFontSize || 24;
        const btnFontWeight = info.btnFontWeight || basicInfo.btnFontWeight || '700';
        const btnScale = info.btnScale !== undefined ? info.btnScale : (basicInfo.btnScale !== undefined ? basicInfo.btnScale : 1.0);
        
        if (btnColor) {
          // 为所有按钮应用自定义背景色
          const allButtons = document.querySelectorAll('.info-card .btn');
          allButtons.forEach(btn => {
            btn.style.background = btnColor;
            btn.style.boxShadow = `0 10px 30px ${btnColor}66, 0 4px 12px ${btnColor}33`;
            btn.style.opacity = btnOpacity;
          });
        }
        
        if (btnTextColor) {
          // 为所有按钮应用自定义文本色
          const allButtons = document.querySelectorAll('.info-card .btn');
          allButtons.forEach(btn => {
            btn.style.color = btnTextColor;
          });
        }
        
        // 应用自定义字体样式
        const allButtons = document.querySelectorAll('.info-card .btn');
        allButtons.forEach(btn => {
          btn.style.fontSize = btnFontSize + 'px';
          btn.style.fontWeight = btnFontWeight;
        });
        
        // 应用按钮容器缩放
        const buttonGroup = document.querySelector('.info-card .button-group');
        if (buttonGroup && btnScale !== 1.0) {
          buttonGroup.style.transform = `scale(${btnScale})`;
          buttonGroup.style.transformOrigin = 'center center';
        }
        
        if (info.btn1Jump && info.btn1Jump.trim()) {
          // 如果设置了链接，隐藏复制按钮，显示链接按钮
          if (btnCopy) {
            btnCopy.style.display = 'none';
          }
          if (btnLink) {
            btnLink.style.display = 'inline-block';
            btnLink.href = info.btn1Jump;
            btnLink.textContent = info.btn1Text || '了解更多';
            // 应用自定义颜色到链接按钮
            if (btnColor) {
              btnLink.style.background = btnColor;
              btnLink.style.boxShadow = `0 10px 30px ${btnColor}66, 0 4px 12px ${btnColor}33`;
              btnLink.style.opacity = btnOpacity;
            }
            if (btnTextColor) {
              btnLink.style.color = btnTextColor;
            }
          }
        } else {
          // 如果没有设置链接，显示复制按钮，隐藏链接按钮
          if (btnCopy) {
            btnCopy.style.display = 'inline-block';
          }
          if (btnLink) {
            btnLink.style.display = 'none';
          }
        }
        
        document.title = info.name ? info.name + '的微信名片' : '微信名片';
        
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
        const margin = section.margin || 0;
        const padding = 0;
        const borderRadius = section.borderRadius !== undefined ? section.borderRadius : 12;
        const borderRadiusStyle = `border-radius: ${borderRadius}px !important;`;
        
        // 为标题组件创建特殊的样式，不设置 padding
        let containerStyle = `style="margin-left: ${margin}px !important; margin-right: ${margin}px !important; margin-top: 0 !important; margin-bottom: 0 !important; width: calc(100% - ${margin * 2}px) !important; ${borderRadiusStyle}"`;
        // 为其他组件使用完整的样式
        const fullContainerStyle = `style="margin-left: ${margin}px !important; margin-right: ${margin}px !important; margin-top: 0 !important; margin-bottom: 0 !important; padding: 0 !important; width: calc(100% - ${margin * 2}px) !important; ${borderRadiusStyle}"`;
        
        switch (section.type) {
          case 'title':
            html += this.renderTitleSection(section, logoUrl, containerStyle);
            break;
          case 'image':
            const imageId = 'image_' + Date.now() + Math.floor(Math.random() * 1000);
            html += '<div ' + fullContainerStyle + ' data-jump="' + (this.getAbsoluteUrl(section.jump) || '') + '" data-zoomable="' + (section.zoomable ? 'true' : 'false') + '">' +
                    '<img id="' + imageId + '" src="' + this.getAbsoluteUrl(section.src) + '" alt="" loading="lazy" style="width: 100%; height: auto; object-fit: contain;">' +
                    '</div>';
            break;
          case 'video':
            const videoId = 'video_' + Date.now() + Math.floor(Math.random() * 1000);
            html += '<div ' + fullContainerStyle + '>' +
                    '<video id="' + videoId + '" src="' + this.getAbsoluteUrl(section.src) + '" poster="' + (this.getAbsoluteUrl(section.poster) || '') + '" controls playsinline webkit-playsinline style="width: 100%; height: auto; object-fit: contain;"></video>' +
                    '</div>';
            break;
          case 'grid':
            const gridPadding = section.padding !== undefined ? section.padding : 0;
            const gridGap = section.gap !== undefined ? section.gap : 4;
            const gridBorderRadius = section.borderRadius !== undefined ? section.borderRadius : 12;
            html += '<div ' + fullContainerStyle + '>';
            html += '<div class="image-grid" style="--grid-padding: ' + gridPadding + 'px; --grid-gap: ' + gridGap + 'px; border-radius: ' + gridBorderRadius + 'px; overflow: hidden;">';
            section.images.forEach((img) => {
              html += '<div class="image-grid-item" data-jump="' + (this.getAbsoluteUrl(img.jump) || '') + '">' +
                      '<img src="' + this.getAbsoluteUrl(img.src) + '" alt="" loading="lazy">' +
                      '</div>';
            });
            html += '</div>';
            html += '</div>';
            break;
          case 'carousel':
            html += this.renderCarouselSection(section, fullContainerStyle, borderRadiusStyle);
            break;
          case 'tabs':
            html += this.renderTabsSection(section, index, fullContainerStyle, borderRadiusStyle);
            break;
          case 'iconRow':
            html += this.renderIconRowSection(section, fullContainerStyle, borderRadiusStyle);
            break;
          case 'notice':
            html += this.renderNoticeCard(section, fullContainerStyle, borderRadiusStyle);
            break;
          case 'code':
            html += '<div ' + fullContainerStyle + '>';
            if (section.html) {
              html += section.html;
            }
            if (section.js) {
              html += '<script>' + section.js + '</script>';
            }
            if (section.css) {
              html += '<style>' + section.css + '</style>';
            }
            html += '</div>';
            break;
          case 'spacer':
            const spacerHeight = section.height || 20;
            html += '<div class="spacer-section" style="height: ' + spacerHeight + 'px; width: 100%;"></div>';
            break;
          case 'pdf':
            const pdfHeight = section.height || 600;
            const pdfId = 'pdf-container-' + Date.now() + Math.floor(Math.random() * 1000);
            html += '<div class="pdf-section" style="width: 100%;">' +
                    '<div class="pdf-viewer" id="' + pdfId + '" style="width: 100%; background: #f7fafc; border-radius: 8px; overflow: hidden;"></div>' +
                    '</div>';
            setTimeout(() => {
              this.renderPDF(this.getAbsoluteUrl(section.src), pdfId, pdfHeight);
            }, 100);
            break;
          case 'footer':
            const footerMargin = section.margin || 0;
            html += '<div class="footer-section" style="margin-left: ' + footerMargin + 'px; margin-right: ' + footerMargin + 'px; padding: 0; width: calc(100% - ' + (footerMargin * 2) + 'px);">' +
                    '<img src="' + this.getAbsoluteUrl(section.src) + '" alt="" loading="lazy" style="width: 100%; height: auto; object-fit: cover; border-radius: 0 0 20px 20px;">' +
                    '</div>';
            break;
          case 'imageGridLink':
            html += this.renderImageGridLinkSection(section, fullContainerStyle);
            break;
          case 'imageButton':
            html += this.renderImageButtonSection(section, fullContainerStyle);
            break;
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
          html += '<img src="' + this.getAbsoluteUrl(icon.src) + '" alt="' + (icon.name || '') + '" loading="lazy" style="max-width:' + maxSize + 'px;max-height:' + maxSize + 'px;">';
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

    renderImageButtonSection(section, contentStyle) {
      const imageButtonId = 'imageButton_' + Date.now() + Math.floor(Math.random() * 1000);
      let html = '<div ' + contentStyle + '>';
      html += '<div id="' + imageButtonId + '" class="image-button-container" style="position: relative; width: 100%;">';
      html += '<img src="' + this.getAbsoluteUrl(section.src) + '" alt="" loading="lazy" style="width: 100%; height: auto; object-fit: contain; display: block;">';
      
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
            backgroundStyle = 'background-color: #ff0000 !important; background-image: url("' + imageUrl + '") !important; background-position: center center !important; background-size: cover !important; background-repeat: no-repeat !important; ';
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
            html += '<img src="' + imageUrl + '" style="position: absolute !important; top: 0 !important; left: 0 !important; width: 100% !important; height: 100% !important; object-fit: cover !important; border-radius: ' + (borderRadius - 1) + 'px !important; z-index: -1 !important;">';
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
      const borderRadius = section.borderRadius || 12;
      const links = section.links || {};
      
      let html = '<div ' + contentStyle + '>';
      html += '<div id="' + gridLinkId + '" class="image-grid-link-container" style="position: relative; width: 100%; overflow: hidden; border-radius: ' + borderRadius + 'px;">';
      html += '<img src="' + this.getAbsoluteUrl(section.src) + '" alt="" loading="lazy" style="width: 100%; height: auto; object-fit: contain; display: block;">';
      
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
      const colorStyle = color ? 'style="background: ' + color + '; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;"' : '';
      
      // New style format support
      const backgroundColor = section.backgroundColor || '';
      const borderColor = section.borderColor || '';
      const borderRadius = section.borderRadius !== undefined ? section.borderRadius : 8;
      const topSpacing = section.topSpacing !== undefined ? section.topSpacing : 0;
      const bottomSpacing = section.bottomSpacing !== undefined ? section.bottomSpacing : 0;
      
      // Build inline styles for the section container
      let containerStyles = [];
      
      // Parse the existing styles from spacingStyle
      if (spacingStyle) {
        const styleMatch = spacingStyle.match(/style="([^"]+)"/);
        if (styleMatch && styleMatch[1]) {
          const styles = styleMatch[1].split(';');
          styles.forEach(style => {
            if (style.trim() && !style.trim().startsWith('margin-top') && !style.trim().startsWith('margin-bottom')) {
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
      if (borderRadius !== 8) {
        containerStyles.push('border-radius: ' + borderRadius + 'px');
      }
      if (topSpacing !== 0) {
        containerStyles.push('margin-top: ' + topSpacing + 'px !important');
      }
      if (bottomSpacing !== 0) {
        containerStyles.push('margin-bottom: ' + bottomSpacing + 'px !important');
      }
      const containerStyleAttr = containerStyles.length > 0 ? 'style="' + containerStyles.join(';') + ';"' : '';
      
      if (level === 1) {
        let html = '<div class="section-title level-1';
        if (section.decorationColor) {
          html += ' has-decoration';
        }
        html += '" ' + containerStyleAttr + '>';
        const titleColorStyle = color ? 'style="color: ' + color + ';"' : '';
        html += '<span class="title-text" ' + titleColorStyle + '>' + (section.title || '') + '</span>';
        if (section.decorationColor) {
          html += '<div class="title-decoration" style="background: ' + section.decorationColor + ';"></div>';
        }
        if (section.subtitle) {
          html += '<div class="title-subtitle">' + section.subtitle + '</div>';
        }
        html += '</div>';
        return html;
      } else if (level === 2) {
        // 二级标题：居左、右侧带logo
        const height = section.height !== undefined ? section.height : 0;
        let heightStyle = '';
        if (height > 0) {
          heightStyle = 'height: ' + height + 'px; display: flex; align-items: center;';
        }
        let level2ContainerStyle = containerStyleAttr;
        if (height > 0) {
          if (level2ContainerStyle) {
            level2ContainerStyle = level2ContainerStyle.replace('style="', 'style="' + heightStyle);
          } else {
            level2ContainerStyle = 'style="' + heightStyle + '"';
          }
        }
        let html = '<div class="section-title level-2" ' + level2ContainerStyle + '>';
        html += '<span class="title-text" ' + colorStyle + '>' + (section.title || '') + '</span>';
        if (titleLogo) {
          html += '<img class="title-logo" src="' + this.getAbsoluteUrl(titleLogo) + '" alt="Logo">';
        }
        html += '</div>';
        return html;
      } else if (level === 3) {
        // 三级标题：居左、左侧带logo
        let html = '<div class="section-title level-3" ' + containerStyleAttr + '>';
        html += '<span class="title-text" ' + colorStyle + '>' + (section.title || '') + '</span>';
        html += '</div>';
        return html;
      }
    },
    
    renderCarouselSection(section, contentStyle, borderRadiusStyle) {
      const carouselId = 'carousel_' + Date.now() + Math.floor(Math.random() * 1000);
      const autoplay = section.autoplay || false;
      const interval = section.interval || 3000;
      const margin = section.margin || 0;
      
      const carouselStyle = `style="margin-left: ${margin}px; margin-right: ${margin}px; width: calc(100% - ${margin * 2}px); ${borderRadiusStyle}"`;
      
      let html = '<div class="carousel" id="' + carouselId + '" ' + carouselStyle + '>';
      html += '<div class="carousel-container">';
      
      section.items.forEach((item, index) => {
        html += '<div class="carousel-item" data-jump="' + (this.getAbsoluteUrl(item.jump) || '') + '">';
        html += '<img src="' + this.getAbsoluteUrl(item.src) + '" alt="' + (item.title || '') + '" style="border-radius: inherit;">';
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
      function setupCarousel() {
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

        function updateCarouselHeight() {
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
        }

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
        function goToSlide(index) {
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
        }
        
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
        
        document.addEventListener('mousemove', (e) => {
          if (!isMouseDragging) return;
          const diffX = e.clientX - mouseStartX;
          mouseDragOffsetX = diffX;
          container.style.transform = `translateX(${-(currentIndex * itemWidth) + mouseDragOffsetX}px)`;
        });
        
        document.addEventListener('mouseup', () => {
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
        });
        
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
        window.addEventListener('resize', () => {
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
        });
      }
      
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
          const tabMargin = tabSection.margin || 0;
          const tabBorderRadius = tabSection.borderRadius !== undefined ? tabSection.borderRadius : 0;
          const tabContainerStyle = `style="margin: ${tabMargin}px !important; padding: 0 !important; border-radius: ${tabBorderRadius}px !important;"`;
          
          switch (tabSection.type) {
            case 'title':
              // 为标签页内的标题组件创建样式
              const tabTitleMargin = tabSection.margin || 0;
              const tabTitleStyle = `style="margin-left: ${tabTitleMargin}px !important; margin-right: ${tabTitleMargin}px !important; margin-top: 0 !important; margin-bottom: 0 !important; width: calc(100% - ${tabTitleMargin * 2}px) !important;"`;
              html += this.renderTitleSection(tabSection, '', tabTitleStyle);
              break;
            case 'image':
              html += '<div ' + tabContainerStyle + ' data-jump="' + (this.getAbsoluteUrl(tabSection.jump) || '') + '">' +
                      '<img src="' + this.getAbsoluteUrl(tabSection.src) + '" alt="" loading="lazy" style="width: 100%; height: auto; max-height: 100%; object-fit: contain; border-radius: inherit;">' +
                      '</div>';
              break;
            case 'video':
              const videoId = 'video_' + Date.now() + Math.floor(Math.random() * 1000);
              html += '<div ' + tabContainerStyle + '>' +
                      '<video id="' + videoId + '" src="' + this.getAbsoluteUrl(tabSection.src) + '" poster="' + (this.getAbsoluteUrl(tabSection.poster) || '') + '" controls playsinline webkit-playsinline style="width: 100%; height: auto; object-fit: contain; border-radius: inherit;"></video>' +
                      '</div>';
              break;
            case 'grid':
              const tabGridPadding = tabSection.padding !== undefined ? tabSection.padding : 0;
              const tabGridGap = tabSection.gap !== undefined ? tabSection.gap : 4;
              const tabGridBorderRadius = tabSection.borderRadius !== undefined ? tabSection.borderRadius : 12;
              html += '<div ' + tabContainerStyle + '>';
              html += '<div class="image-grid" style="--grid-padding: ' + tabGridPadding + 'px; --grid-gap: ' + tabGridGap + 'px; border-radius: ' + tabGridBorderRadius + 'px; overflow: hidden;">';
              tabSection.images.forEach((img) => {
                html += '<div class="image-grid-item" data-jump="' + (this.getAbsoluteUrl(img.jump) || '') + '">' +
                        '<img src="' + this.getAbsoluteUrl(img.src) + '" alt="" loading="lazy">' +
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
                  html += '<img src="' + this.getAbsoluteUrl(item.src) + '" alt="' + (item.title || '') + '" loading="lazy" style="border-radius: inherit;">';
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
      
      const isWechat = typeof WechatJSSDK !== 'undefined' && WechatJSSDK.isWechat();
      
      videos.forEach((video, index) => {
        console.log(`处理视频 ${index + 1}:`, video.src);
        // 如果已经设置了poster，跳过
        if (video.poster && video.poster.length > 10) {
          console.log('视频已有poster，跳过');
          return;
        }
        
        // 确保视频有preload属性
        video.preload = 'metadata';
        
        // 对于微信浏览器，提供更好的处理策略
        const trySetPoster = () => {
          console.log(`尝试为视频 ${index + 1} 生成封面，readyState:`, video.readyState);
          
          // 首先尝试通过事件监听获取
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
          
          // 监听多种事件以提高成功率
          video.addEventListener('loadeddata', tryGenerateCover, { once: true });
          video.addEventListener('loadedmetadata', () => {
            console.log('loadedmetadata事件触发');
            // 在微信中，我们尝试更谨慎的方式
            setTimeout(() => {
              tryGenerateCover();
            }, 200);
          }, { once: true });
          
          // 也尝试监听canplay事件
          video.addEventListener('canplay', tryGenerateCover, { once: true });
          
          // 直接尝试加载视频
          try {
            video.load();
          } catch (e) {
            console.log('video.load() 失败');
          }
          
          // 设置一个超时，确保有一个兜底方案
          setTimeout(() => {
            if (!setCoverAttempted) {
              tryGenerateCover();
            }
          }, 1500);
        };
        
        // 稍微延迟执行，确保DOM就绪
        setTimeout(() => trySetPoster(), 150);
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
      
      if (!shareIcon) {
        shareIcon = info.logo || '';
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
        
        const response = await fetch(signUrl);
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

    copyToClipboard(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        // 使用现代的Clipboard API
        navigator.clipboard.writeText(text).then(() => {
          this.showToast('信息已复制到剪贴板', 'success');
        }).catch(() => {
          this.fallbackCopy(text);
        });
      } else {
        // 使用传统的方法作为后备
        this.fallbackCopy(text);
      }
    },

    fallbackCopy(text) {
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
        this.showToast('信息已复制到剪贴板', 'success');
      } catch (e) {
        this.showToast('复制失败，请手动复制', 'error');
      }
      
      document.body.removeChild(textArea);
    },

    handleCall() {
      if (navigator.vibrate) navigator.vibrate(50);
      if (this.config.settings && this.config.settings.showCallConfirm) {
        this.showCallConfirm();
      } else {
        this.doCall();
      }
    },

    showCallConfirm() {
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      const phone = contactSection ? contactSection.phone : this.config.basicInfo.phone;
      document.getElementById('confirmPhone').textContent = phone;
      document.getElementById('callConfirm').classList.add('show');
    },

    hideCallConfirm() {
      document.getElementById('callConfirm').classList.remove('show');
    },

    doCall() {
      this.hideCallConfirm();
      const contactSection = this.config.sections && this.config.sections.find(section => section.type === 'contact');
      const phone = contactSection ? contactSection.phone : this.config.basicInfo.phone;
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
