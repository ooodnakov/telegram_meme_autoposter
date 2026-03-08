interface MediaCardProps {
  src: string;
  type: "image" | "video";
  caption?: string;
  source?: string;
  actions?: React.ReactNode;
}

const MediaCard = ({ src, type, caption, source, actions }: MediaCardProps) => {
  return (
    <div className="glass-card overflow-hidden group hover:border-primary/30 transition-all duration-300">
      <div className="aspect-square bg-secondary/50 overflow-hidden">
        {type === "image" ? (
          <img
            src={src}
            alt={caption || "media"}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <div className="text-center">
              <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center mx-auto mb-2">
                <svg className="w-5 h-5 text-primary" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </div>
              <p className="text-xs text-muted-foreground">Video</p>
            </div>
          </div>
        )}
      </div>
      <div className="p-4">
        {caption && (
          <p className="text-sm text-foreground truncate mb-1">{caption}</p>
        )}
        {source && (
          <p className="text-xs text-muted-foreground">from {source}</p>
        )}
        {actions && <div className="mt-3 flex gap-2">{actions}</div>}
      </div>
    </div>
  );
};

export default MediaCard;
