'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

const ScrollArea = ({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => {
  return (
    <div
      data-slot='scroll-area'
      className={cn('relative overflow-y-auto', className)}
      {...props}
    >
      {children}
    </div>
  );
};

export { ScrollArea };
