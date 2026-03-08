import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

interface ClickableImageProps {
  src: string;
  alt: string;
  className?: string;
}

const ClickableImage = ({ src, alt, className }: ClickableImageProps) => {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          className="block h-full w-full cursor-zoom-in overflow-hidden"
          aria-label={`Open image preview: ${alt}`}
        >
          <img src={src} alt={alt} className={className} />
        </button>
      </DialogTrigger>
      <DialogContent
        className="w-[95vw] max-w-[95vw] cursor-zoom-out border-none bg-transparent p-0 shadow-none sm:rounded-none"
        onClick={() => setOpen(false)}
      >
        <DialogTitle className="sr-only">{alt}</DialogTitle>
        <DialogDescription className="sr-only">
          Click anywhere on the preview to close it.
        </DialogDescription>
        <img
          src={src}
          alt={alt}
          className="max-h-[90vh] w-full rounded-lg object-contain"
        />
      </DialogContent>
    </Dialog>
  );
};

export default ClickableImage;
