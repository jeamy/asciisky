// Small DOM helpers: every text goes in as a text node, never as HTML.
const SVG_NS = 'http://www.w3.org/2000/svg';

export function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    applyProps(node, props);
    appendChildren(node, children);
    return node;
}

export function svgEl(tag, attrs = {}, ...children) {
    const node = document.createElementNS(SVG_NS, tag);
    applyProps(node, attrs);
    appendChildren(node, children);
    return node;
}

function applyProps(node, props) {
    for (const [key, value] of Object.entries(props || {})) {
        if (value == null || value === false) continue;
        if (key === 'class') node.setAttribute('class', value);
        else if (key === 'text') node.textContent = value;
        else if (key === 'dataset') Object.assign(node.dataset, value);
        else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
        else if (value === true) node.setAttribute(key, '');
        else node.setAttribute(key, String(value));
    }
}

function appendChildren(node, children) {
    for (const child of children.flat(Infinity)) {
        if (child == null || child === false) continue;
        node.append(child instanceof Node ? child : String(child));
    }
}

/** Run ``fn`` at most once per animation frame. */
export function frameThrottle(fn) {
    let pending = false;
    return () => {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => {
            pending = false;
            fn();
        });
    };
}
