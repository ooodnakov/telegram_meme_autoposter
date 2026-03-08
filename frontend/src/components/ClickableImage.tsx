import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";

interface ClickableImageProps {
  src: string;
  alt: string;
  className?: string;
}

const ClickableImage = ({ src, alt, className }: ClickableImageProps) => {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className="block h-full w-full cursor-zoom-in overflow-hidden"
          aria-label={`Open image preview: ${alt}`}
        >
          <img src={src} alt={alt} className={className} />
        </button>
      </DialogTrigger>
      <DialogContent className="w-[95vw] max-w-[95vw] border-none bg-transparent p-0 shadow-none sm:rounded-none">
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
