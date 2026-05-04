'use client';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useModels } from '@/features/chat/hooks/useModels';
import type { ChatModel } from '@/features/chat/types';

interface ModelSelectorProps {
  selectedModelId: string;
  onModelChange: (modelId: string) => void;
  disabled?: boolean;
}

const ModelSelector = ({
  selectedModelId,
  onModelChange,
  disabled,
}: ModelSelectorProps) => {
  const { data: models, isLoading, isError } = useModels();

  if (isError) {
    return (
      <span className='text-xs text-[#ffb4ab]'>Failed to load models</span>
    );
  }

  return (
    <Select
      value={selectedModelId}
      onValueChange={onModelChange}
      disabled={disabled || isLoading}
    >
      <SelectTrigger className='w-55 border-[#2a2a3d] bg-[#1e1e2e] text-[#e4e1ed] focus:ring-[#494bd6]'>
        <SelectValue placeholder={isLoading ? 'Loading models…' : 'Select model'} />
      </SelectTrigger>
      <SelectContent className='border-[#2a2a3d] bg-[#1e1e2e] text-[#e4e1ed]'>
        {models?.map((model: ChatModel) => (
          <SelectItem
            key={model.id}
            value={model.id}
            className='focus:bg-[#2a2a3d] focus:text-[#e4e1ed]'
          >
            <span className='font-medium'>{model.name}</span>
            <span className='ml-2 text-xs text-[#6b6b8a]'>{model.provider}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};

export default ModelSelector;
