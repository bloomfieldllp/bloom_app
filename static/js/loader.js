/* =========================================================
   BLOOM LOADER — STATE MACHINE (CORRECTED CHOREOGRAPHY)
   ========================================================= */

const CLIPS = [
    {
        text:   "Design is the silent ambassador of your brand.",
        author: "Paul Rand",
        image:  "/static/images/loader-01.png"
    },
    {
        text:   "Good design is good business.",
        author: "Thomas J. Watson Jr.",
        image:  "/static/images/loader-02.png"
    },
    {
        text:   "The life of a designer is a life of fight: fight against the ugliness.",
        author: "Massimo Vignelli",
        image:  "/static/images/loader-03.png"
    }
];

/* Timings in milliseconds */
const T = {
    TYPE_SPEED:         58,     // ms per character
    NORMAL_HOLD:      1600,     // hold after normal quote finishes typing
    A_TO_B_DURATION:  1900,     // duration of spatial shrink + image crossfade
    RECTANGLE_HOLD:    300,     // hold small rectangle before collapsing
    COLLAPSE_DURATION: 450,     // duration to collapse rectangle to thin vertical line
    STATE_B_DELAY:     350,     // delay between collapse and typing cursor appearance
    IMAGE_HOLD:       1400,     // hold after image-filled quote finishes typing
    B_TO_A_DURATION:  2400,     // duration of growth + image texture crossfade
    NEXT_A_SETTLE:     100,     // delay after B→A resolves before next normal quote typing
};

const DOM = {
    loader:             document.getElementById("bloom-loader"),
    bgA:                document.getElementById("lBgA"),
    shrinkWrap:         document.getElementById("lShrinkWrap"),
    shrinkImgA:         document.getElementById("lShrinkImgA"),
    shrinkImgB:         document.getElementById("lShrinkImgB"),
    stateBStage:        document.getElementById("lStateBStage"),
    imageTextWrap:      document.getElementById("lImageTextWrap"),
    imageTextA:         document.getElementById("lImageTextA"),
    imageTextB:         document.getElementById("lImageTextB"),
    imageTextContentA:  document.getElementById("lImageTextContentA"),
    imageTextContentB:  document.getElementById("lImageTextContentB"),
    imageTextCursor:    document.getElementById("lImageTextCursor"),
    normal:             document.getElementById("lNormal"),
    quoteText:          document.getElementById("lQuoteText"),
    quoteCursor:        document.getElementById("lQuoteCursor"),
    author:             document.getElementById("lAuthor"),
};

const SM = {
    currentIdx: 0,
    epoch: 0,
    phase: "IDLE"
};

function getNextIdx(offset = 1) {
    return (SM.currentIdx + offset) % CLIPS.length;
}

function preloadAllImages() {
    const promises = CLIPS.map(clip => {
        return new Promise((resolve) => {
            const img = new Image();
            img.src = clip.image;
            img.onload = () => {
                if (img.decode) {
                    img.decode().then(resolve).catch(resolve);
                } else {
                    resolve();
                }
            };
            img.onerror = resolve; // Resolve anyway to avoid blocking execution
        });
    });
    return Promise.all(promises);
}

function setImage(el, url) {
    el.style.backgroundImage = `url("${url}")`;
}

function show(el) { el.style.opacity = "1"; }
function hide(el) { el.style.opacity = "0"; }

function fadeIn(el, durationMs) {
    el.style.transition = `opacity ${durationMs}ms ease`;
    el.style.opacity = "1";
}

function fadeOut(el, durationMs) {
    el.style.transition = `opacity ${durationMs}ms ease`;
    el.style.opacity = "0";
}

function clearTransition(el) {
    el.style.transition = "";
}

function startTyping(targets, text, speed, epoch, onDone) {
    let pos = 0;
    targets.forEach(el => el.textContent = "");

    function tick() {
        if (SM.epoch !== epoch) return;

        if (pos >= text.length) {
            onDone();
            return;
        }

        const char = text[pos];
        targets.forEach(el => el.textContent += char);
        pos++;
        setTimeout(tick, speed);
    }

    setTimeout(tick, speed);
}

/* =========================================================
   STATE A — NORMAL LOADER
========================================================= */
function enterStateA() {
    SM.phase = "NORMAL_A";
    SM.epoch++;
    const epoch = SM.epoch;

    const clip = CLIPS[SM.currentIdx];

    // Reset stages
    hide(DOM.shrinkWrap);
    clearTransition(DOM.shrinkWrap);
    DOM.shrinkWrap.style.clipPath = "inset(0 0 0 0 round 0px)";

    hide(DOM.stateBStage);
    clearTransition(DOM.stateBStage);
    DOM.imageTextWrap.style.transform = "scale(1)";
    DOM.imageTextWrap.style.transition = "";
    DOM.imageTextB.style.opacity = "0";
    DOM.imageTextB.style.transition = "";

    DOM.imageTextContentA.textContent = "";
    DOM.imageTextContentB.textContent = "";
    DOM.imageTextCursor.classList.remove("active");

    // Set A background
    setImage(DOM.bgA, clip.image);
    fadeIn(DOM.bgA, 600);

    // Reset normal content
    DOM.quoteText.textContent = "";
    DOM.author.textContent = `— ${clip.author}`;
    DOM.author.classList.remove("visible");
    DOM.quoteCursor.classList.remove("active");

    fadeIn(DOM.normal, 400);

    // Delay slightly before cursor & typing start
    setTimeout(() => {
        if (SM.epoch !== epoch) return;
        DOM.quoteCursor.classList.add("active");

        startTyping(
            [DOM.quoteText],
            clip.text,
            T.TYPE_SPEED,
            epoch,
            () => {
                if (SM.epoch !== epoch) return;
                DOM.quoteCursor.classList.remove("active");
                DOM.author.classList.add("visible");

                // Hold before A -> B shrink
                setTimeout(() => {
                    if (SM.epoch !== epoch) return;
                    enterAtoBShrink();
                }, T.NORMAL_HOLD);
            }
        );
    }, 150);
}

/* =========================================================
   A → B TRANSITION
========================================================= */
function enterAtoBShrink() {
    SM.phase = "A_TO_B_SHRINK";
    SM.epoch++;
    const epoch = SM.epoch;

    const curClip = CLIPS[SM.currentIdx];
    const nextClip = CLIPS[getNextIdx(1)];

    // Setup shrink wrap container and backgrounds
    setImage(DOM.shrinkImgA, curClip.image);
    setImage(DOM.shrinkImgB, nextClip.image);

    DOM.shrinkImgA.style.transition = "";
    DOM.shrinkImgB.style.transition = "";
    show(DOM.shrinkImgA);
    hide(DOM.shrinkImgB);

    DOM.shrinkWrap.style.transition = "";
    DOM.shrinkWrap.style.clipPath = "inset(0% 0% 0% 0% round 0px)";
    show(DOM.shrinkWrap);

    // Hide background A instantly since shrinkWrap matches it exactly
    hide(DOM.bgA);
    clearTransition(DOM.bgA);

    // Fade out Quote 1 smoothly
    fadeOut(DOM.normal, T.A_TO_B_DURATION * 0.6);

    // Trigger spatial shrink
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            if (SM.epoch !== epoch) return;

            const shrinkEase = "cubic-bezier(0.76, 0, 0.24, 1)";
            DOM.shrinkWrap.style.transition = `clip-path ${T.A_TO_B_DURATION}ms ${shrinkEase}`;
            // Shrinks to a small centered rectangle
            DOM.shrinkWrap.style.clipPath = "inset(42% 15% 42% 15% round 4px)";

            // Crossfade Image 1 -> Image 2 inside the rectangle
            const xfadeDelay = T.A_TO_B_DURATION * 0.15;
            const xfadeDur = T.A_TO_B_DURATION * 0.75;
            setTimeout(() => {
                if (SM.epoch !== epoch) return;
                DOM.shrinkImgA.style.transition = `opacity ${xfadeDur}ms ease`;
                DOM.shrinkImgB.style.transition = `opacity ${xfadeDur}ms ease`;
                hide(DOM.shrinkImgA);
                show(DOM.shrinkImgB);
            }, xfadeDelay);
        });
    });

    // STEP 8: Small rectangle remains momentarily, then collapses horizontally
    setTimeout(() => {
        if (SM.epoch !== epoch) return;
        enterRectangleCollapse(epoch, nextClip);
    }, T.A_TO_B_DURATION + T.RECTANGLE_HOLD);
}

function enterRectangleCollapse(epoch, nextClip) {
    SM.phase = "RECTANGLE_COLLAPSE";

    const collapseEase = "cubic-bezier(0.25, 1, 0.5, 1)";
    DOM.shrinkWrap.style.transition = `clip-path ${T.COLLAPSE_DURATION}ms ${collapseEase}, opacity ${T.COLLAPSE_DURATION}ms ease`;
    
    // Collapse horizontally into a thin vertical line in center
    DOM.shrinkWrap.style.clipPath = "inset(42% 49.9% 42% 49.9% round 0px)";

    // Once collapsed, fade out completely to expose pure white background
    setTimeout(() => {
        if (SM.epoch !== epoch) return;
        hide(DOM.shrinkWrap);
        clearTransition(DOM.shrinkWrap);
        enterStateBCursor(nextClip);
    }, T.COLLAPSE_DURATION);
}

/* =========================================================
   STATE B — IMAGE-FILLED TYPOGRAPHY
========================================================= */
function enterStateBCursor(clip) {
    SM.phase = "STATE_B_CURSOR";
    SM.epoch++;
    const epoch = SM.epoch;

    hide(DOM.normal);
    clearTransition(DOM.normal);

    // Setup image fills
    setImage(DOM.imageTextContentA, clip.image);
    // Prepare the next clip for imageTextB (the clip to crossfade to during B->A)
    const destClip = CLIPS[getNextIdx(2)];
    setImage(DOM.imageTextContentB, destClip.image);

    DOM.imageTextContentA.textContent = "";
    DOM.imageTextContentB.textContent = "";
    DOM.imageTextB.style.opacity = "0";

    // Show white stage
    fadeIn(DOM.stateBStage, 250);

    // Delay cursor activation to match visual flow
    setTimeout(() => {
        if (SM.epoch !== epoch) return;
        DOM.imageTextCursor.classList.add("active");

        setTimeout(() => {
            if (SM.epoch !== epoch) return;
            enterStateBTyping(clip, epoch);
        }, T.STATE_B_DELAY);
    }, 100);
}

function enterStateBTyping(clip, epoch) {
    SM.phase = "STATE_B_TYPING";

    startTyping(
        [DOM.imageTextContentA, DOM.imageTextContentB],
        clip.text,
        T.TYPE_SPEED,
        epoch,
        () => {
            if (SM.epoch !== epoch) return;
            DOM.imageTextCursor.classList.remove("active");
            SM.phase = "STATE_B_HOLD";

            setTimeout(() => {
                if (SM.epoch !== epoch) return;
                enterBtoAGrow(clip);
            }, T.IMAGE_HOLD);
        }
    );
}

/* =========================================================
   B → A TRANSITION
========================================================= */
function enterBtoAGrow(curBClip) {
    SM.phase = "B_TO_A_GROW";
    SM.epoch++;
    const epoch = SM.epoch;

    const nextAClip = CLIPS[getNextIdx(2)];

    // Place destination image behind white stage
    setImage(DOM.bgA, nextAClip.image);
    hide(DOM.bgA);
    clearTransition(DOM.bgA);

    // Calculate required scale dynamically to fully cover viewport
    const rect = DOM.imageTextWrap.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Scale must make letters cover width and height with a safety margin
    const scaleX = (vw / (rect.width || 500)) * 26;
    const scaleY = (vh / (rect.height || 100)) * 26;
    const targetScale = Math.max(scaleX, scaleY, 28);

    // Reset transition before setting scale start
    DOM.imageTextWrap.style.transition = "";
    DOM.imageTextWrap.style.transform = "scale(1)";

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            if (SM.epoch !== epoch) return;

            const growEase = "cubic-bezier(0.22, 1, 0.36, 1)";
            DOM.imageTextWrap.style.transition = `transform ${T.B_TO_A_DURATION}ms ${growEase}`;
            DOM.imageTextWrap.style.transform = `scale(${targetScale})`;

            // Smoothly crossfade Text B (Image 3) over Text A (Image 2) during growth
            const fadeStart = T.B_TO_A_DURATION * 0.15;
            const fadeDur = T.B_TO_A_DURATION * 0.7;
            setTimeout(() => {
                if (SM.epoch !== epoch) return;
                DOM.imageTextB.style.transition = `opacity ${fadeDur}ms ease`;
                show(DOM.imageTextB);
            }, fadeStart);

            // Fade in background A behind white stage toward end of growth
            const bgRevealMs = T.B_TO_A_DURATION * 0.72;
            setTimeout(() => {
                if (SM.epoch !== epoch) return;
                fadeIn(DOM.bgA, T.B_TO_A_DURATION * 0.28);
            }, bgRevealMs);

            // Fade out white stage to reveal background A
            const stageFadeMs = T.B_TO_A_DURATION * 0.82;
            setTimeout(() => {
                if (SM.epoch !== epoch) return;
                fadeOut(DOM.stateBStage, T.B_TO_A_DURATION * 0.18);
            }, stageFadeMs);
        });
    });

    // Complete B -> A transition
    setTimeout(() => {
        if (SM.epoch !== epoch) return;
        
        // If a redirect URL is defined (and is not login), exit to the dashboard!
        if (SM.redirectUrl && SM.redirectUrl !== "/login") {
            window.location.href = SM.redirectUrl;
            return;
        }
        
        finishBtoA(nextAClip);
    }, T.B_TO_A_DURATION);
}

function finishBtoA(nextAClip) {
    // Advance index by 2 steps in sequence: A1 -> B2 -> A3 -> B1 -> A2 -> B3 ...
    SM.currentIdx = (SM.currentIdx + 2) % CLIPS.length;

    // Hard-reset white stage layers instantly (now hidden)
    DOM.stateBStage.style.transition = "";
    DOM.stateBStage.style.opacity = "0";

    DOM.imageTextContentA.textContent = "";
    DOM.imageTextContentB.textContent = "";
    DOM.imageTextWrap.style.transform = "scale(1)";
    DOM.imageTextWrap.style.transition = "";
    DOM.imageTextB.style.opacity = "0";
    DOM.imageTextB.style.transition = "";
    DOM.imageTextCursor.classList.remove("active");

    // Clear shrink transitions
    hide(DOM.shrinkWrap);
    clearTransition(DOM.shrinkWrap);
    DOM.shrinkWrap.style.clipPath = "inset(0 0 0 0 round 0px)";

    // Setup bgA directly
    show(DOM.bgA);
    clearTransition(DOM.bgA);

    // Reset normal state elements
    DOM.quoteText.textContent = "";
    DOM.author.textContent = `— ${nextAClip.author}`;
    DOM.author.classList.remove("visible");
    DOM.quoteCursor.classList.remove("active");

    hide(DOM.normal);
    clearTransition(DOM.normal);

    setTimeout(enterStateA, T.NEXT_A_SETTLE);
}

const BloomLoader = {
    requestExit(onComplete) {
        console.log("[BloomLoader] Exit requested — stub, integrate later.");
    },
    stop() {
        SM.phase = "STOPPED";
        SM.epoch++;
    }
};

window.BloomLoader = BloomLoader;

// Initialize state redirect mapping
SM.redirectUrl = null;

// Fetch user destination route in parallel to preloading
const destPromise = fetch("/api/user/destination")
    .then(r => r.json())
    .then(d => {
        if (d && d.redirect_url) {
            SM.redirectUrl = d.redirect_url;
        }
    })
    .catch(() => {
        SM.redirectUrl = null;
    });

Promise.all([preloadAllImages(), destPromise]).then(() => {
    // Start State A only after all images are loaded and destination is fetched
    enterStateA();
});