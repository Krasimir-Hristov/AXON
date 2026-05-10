'use client';

import * as React from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { cn } from '@/lib/utils';

const DialogRoot = Dialog.Root;
const DialogTrigger = Dialog.Trigger;
const DialogClose = Dialog.Close;

const DialogBackdrop = ({
  className,
  ref,
  ...props
}: React.ComponentPropsWithoutRef<typeof Dialog.Backdrop> & {
  ref?: React.Ref<React.ElementRef<typeof Dialog.Backdrop>>;
}) => (
  <Dialog.Backdrop
    ref={ref}
    className={cn(
      'fixed inset-0 z-50 bg-black/60 backdrop-blur-sm',
      'data-starting-style:opacity-0 data-ending-style:opacity-0',
      'transition-opacity duration-150',
      className,
    )}
    {...props}
  />
);

const DialogPopup = ({
  className,
  children,
  ref,
  ...props
}: React.ComponentPropsWithoutRef<typeof Dialog.Popup> & {
  ref?: React.Ref<React.ElementRef<typeof Dialog.Popup>>;
}) => (
  <Dialog.Portal>
    <DialogBackdrop />
    <Dialog.Popup
      ref={ref}
      className={cn(
        'fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2',
        'rounded-xl border border-[#2a2a3d] bg-[#13131f] p-6 shadow-2xl',
        'data-starting-style:scale-95 data-starting-style:opacity-0',
        'data-ending-style:scale-95 data-ending-style:opacity-0',
        'transition-[transform,opacity] duration-150',
        className,
      )}
      {...props}
    >
      {children}
    </Dialog.Popup>
  </Dialog.Portal>
);

const DialogTitle = ({
  className,
  ref,
  ...props
}: React.ComponentPropsWithoutRef<typeof Dialog.Title> & {
  ref?: React.Ref<React.ElementRef<typeof Dialog.Title>>;
}) => (
  <Dialog.Title
    ref={ref}
    className={cn('text-base font-semibold text-[#e4e1ed]', className)}
    {...props}
  />
);

const DialogDescription = ({
  className,
  ref,
  ...props
}: React.ComponentPropsWithoutRef<typeof Dialog.Description> & {
  ref?: React.Ref<React.ElementRef<typeof Dialog.Description>>;
}) => (
  <Dialog.Description
    ref={ref}
    className={cn('mt-1.5 text-sm text-[#6b6b8a]', className)}
    {...props}
  />
);

export {
  DialogRoot,
  DialogTrigger,
  DialogClose,
  DialogPopup,
  DialogTitle,
  DialogDescription,
};
