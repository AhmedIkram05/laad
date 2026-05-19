/*
 * MarkdownRenderer Component
 * --------------------
 * Renders markdown-formatted text with proper styling.
 */

function MarkdownRenderer({content}) {
    if (!content) return null;

    const renderContent = () => {
        const lines = content.split("\n");
        const elements = [];
        let inCodeBlock = false;
        let codeContent = [];
        let listItems = [];
        let inList = false;

        const flushList = () => {
            if (listItems.length > 0) {
                elements.push(
                    <ul key={`list-${elements.length}`} className="md-list">
                        {listItems.map((item, i) => (
                            <li key={i} className="md-list-item">{item}</li>
                        ))}
                    </ul>
                );
                listItems = [];
                inList = false;
            }
        };

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            if (line.startsWith("```")) {
                if (inCodeBlock) {
                    elements.push(
                        <pre key={`code-${elements.length}`} className="md-code-block">
                            <code>{codeContent.join("\n")}</code>
                        </pre>
                    );
                    codeContent = [];
                    inCodeBlock = false;
                } else {
                    flushList();
                    inCodeBlock = true;
                }
                continue;
            }

            if (inCodeBlock) {
                codeContent.push(line);
                continue;
            }

            if (line.match(/^#{1,6}\s/)) {
                flushList();
                const level = line.match(/^#+/)[0].length;
                const text = line.replace(/^#+\s*/, "");
                elements.push(
                    <h key={`h-${elements.length}`} className={`md-h md-h${level}`}>
                        {text}
                    </h>
                );
            } else if (line.match(/^(\d+)\.\s/)) {
                if (!inList) {
                    inList = true;
                }
                const text = line.replace(/^\d+\.\s*/, "");
                listItems.push(renderInline(text));
            } else if (line.match(/^[-*]\s/)) {
                flushList();
                const text = line.replace(/^[-*]\s*/, "");
                if (!inList) {
                    inList = true;
                    listItems = [];
                }
                listItems.push(renderInline(text));
            } else if (line.trim() === "") {
                flushList();
            } else {
                flushList();
                elements.push(
                    <p key={`p-${elements.length}`} className="md-p">
                        {renderInline(line)}
                    </p>
                );
            }
        }

        flushList();
        return elements;
    };

    const renderInline = (text) => {
        const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|-{2}[^-]+-{2})/);
        return parts.map((part, i) => {
            if (part.startsWith("**") && part.endsWith("**")) {
                return <strong key={i} className="md-bold">{part.slice(2, -2)}</strong>;
            }
            if (part.startsWith("*") && part.endsWith("*")) {
                return <em key={i} className="md-italic">{part.slice(1, -1)}</em>;
            }
            if (part.startsWith("`") && part.endsWith("`")) {
                return <code key={i} className="md-inline-code">{part.slice(1, -1)}</code>;
            }
            if (part.startsWith("--") && part.endsWith("--")) {
                return <span key={i} className="md-highlight">{part.slice(2, -2)}</span>;
            }
            return part;
        });
    };

    return <div className="markdown-content">{renderContent()}</div>;
}

export default MarkdownRenderer;