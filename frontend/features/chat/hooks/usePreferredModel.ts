'use client';

import { useEffect, useState } from 'react';
import { createClient } from '@/lib/supabase/client';

const METADATA_KEY = 'preferred_model_id';

interface UsePreferredModelReturn {
  preferredModelId: string;
  loaded: boolean;
  changeModel: (modelId: string) => void;
}

export function usePreferredModel(): UsePreferredModelReturn {
  const [preferredModelId, setPreferredModelId] = useState('');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(({ data }) => {
      const saved = data.user?.user_metadata?.[METADATA_KEY];
      if (typeof saved === 'string' && saved) {
        setPreferredModelId(saved);
      }
      setLoaded(true);
    });
  }, []);

  function changeModel(modelId: string) {
    setPreferredModelId(modelId);
    const supabase = createClient();
    void supabase.auth.updateUser({ data: { [METADATA_KEY]: modelId } });
  }

  return { preferredModelId, loaded, changeModel };
}
