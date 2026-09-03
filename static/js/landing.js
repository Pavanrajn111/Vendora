/**
 * Vendora — Premium 3D Hero Parallax & Scroll Reveal Interactions
 */
document.addEventListener('DOMContentLoaded', function () {
    // 1. Accessibility & Capabilities Check
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

    // 2. 3D Hero Mouse Parallax
    const scene = document.querySelector('.hero-3d-scene');
    const rig = document.querySelector('.hero-3d-rig');

    if (scene && rig && !prefersReducedMotion && !isTouchDevice) {
        let mouseX = 0;
        let mouseY = 0;
        let currentRotX = 6;
        let currentRotY = -10;
        let targetRotX = 6;
        let targetRotY = -10;
        let isHovering = false;
        let animationFrameId = null;

        function updateParallax() {
            if (isHovering) {
                // Smooth interpolation (lerp)
                currentRotX += (targetRotX - currentRotX) * 0.12;
                currentRotY += (targetRotY - currentRotY) * 0.12;
                rig.style.transform = `rotateY(${currentRotY.toFixed(2)}deg) rotateX(${currentRotX.toFixed(2)}deg)`;
                animationFrameId = requestAnimationFrame(updateParallax);
            }
        }

        scene.addEventListener('mouseenter', function () {
            isHovering = true;
            rig.style.animation = 'none'; // Pause idle animation during manual cursor control
            cancelAnimationFrame(animationFrameId);
            animationFrameId = requestAnimationFrame(updateParallax);
        });

        scene.addEventListener('mousemove', function (e) {
            const rect = scene.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width; // 0 to 1
            const y = (e.clientY - rect.top) / rect.height; // 0 to 1

            // Map to rotation angles (-10deg baseline Y, +6deg baseline X)
            targetRotY = -10 + (x - 0.5) * 22;
            targetRotX = 6 - (y - 0.5) * 18;
        });

        scene.addEventListener('mouseleave', function () {
            isHovering = false;
            cancelAnimationFrame(animationFrameId);
            // Smoothly reset and re-enable gentle continuous idle float
            rig.style.transition = 'transform 0.6s cubic-bezier(0.2, 0.8, 0.4, 1)';
            rig.style.transform = 'rotateY(-10deg) rotateX(6deg)';
            setTimeout(() => {
                rig.style.transition = '';
                rig.style.animation = 'heroFloating 6.5s ease-in-out infinite';
            }, 600);
        });
    }

    // 3. Lightweight IntersectionObserver for Scroll Reveals
    const reveals = document.querySelectorAll('.reveal-on-scroll');
    if ('IntersectionObserver' in window && !prefersReducedMotion) {
        const observer = new IntersectionObserver((entries, obs) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-revealed');
                    obs.unobserve(entry.target);
                }
            });
        }, {
            threshold: 0.12,
            rootMargin: '0px 0px -40px 0px'
        });

        reveals.forEach(el => observer.observe(el));
    } else {
        // Fallback: immediately reveal all elements if observer not supported or reduced motion
        reveals.forEach(el => el.classList.add('is-revealed'));
    }

    // 4. Interactive Live Showcase Category Switcher
    const tabBtns = document.querySelectorAll('.showcase-tab-btn');
    const showcaseCards = document.querySelectorAll('.showcase-item-card');

    if (tabBtns.length > 0 && showcaseCards.length > 0) {
        tabBtns.forEach(btn => {
            btn.addEventListener('click', function () {
                const category = this.getAttribute('data-category');

                // Update tab styles
                tabBtns.forEach(b => {
                    b.classList.remove('bg-gradient-to-r', 'from-red-500', 'to-orange-500', 'text-white', 'shadow-lg');
                    b.classList.add('glass-panel', 'text-muted');
                });
                this.classList.remove('glass-panel', 'text-muted');
                this.classList.add('bg-gradient-to-r', 'from-red-500', 'to-orange-500', 'text-white', 'shadow-lg');

                // Filter showcase cards
                showcaseCards.forEach(card => {
                    const cardCat = card.getAttribute('data-category');
                    if (category === 'all' || cardCat === category) {
                        card.classList.remove('hidden');
                        card.classList.add('fade-in');
                    } else {
                        card.classList.add('hidden');
                        card.classList.remove('fade-in');
                    }
                });
            });
        });
    }
});
