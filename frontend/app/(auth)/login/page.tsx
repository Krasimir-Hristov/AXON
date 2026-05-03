import LoginButton from '@/features/auth/components/LoginButton';

const LoginPage = () => {
  return (
    <main className='relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-[#13131b]'>
      {/* Neural network dot grid */}
      <div
        className='pointer-events-none absolute inset-0 opacity-10'
        style={{
          backgroundImage:
            'radial-gradient(circle at center, rgba(192,193,255,0.4) 1px, transparent 1px)',
          backgroundSize: '32px 32px',
        }}
      />
      {/* Ambient glow */}
      <div className='pointer-events-none absolute left-1/2 top-1/2 h-100 w-100 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#494bd6]/10 blur-[120px]' />

      {/* Content */}
      <div className='relative z-10 flex w-full max-w-100 flex-col items-center px-6'>
        {/* Wordmark */}
        <div className='mb-12 flex flex-col items-center text-center'>
          <h1
            className='mb-2 bg-linear-to-r from-[#c0c1ff] to-[#8083ff] bg-clip-text text-[40px] font-semibold leading-tight tracking-[-0.02em] text-transparent'
            style={{ fontFamily: 'var(--font-space-grotesk)' }}
          >
            AXON
          </h1>
          <p className='text-base leading-relaxed text-[#c7c4d7]'>
            Your AI Personal Assistant
          </p>
        </div>

        {/* Glassmorphism card */}
        <div className='w-full rounded-xl border border-[#464554]/50 bg-[#1f1f27]/40 p-6 shadow-[0_0_30px_rgba(73,75,214,0.05)] backdrop-blur-xl'>
          <LoginButton />
        </div>

        {/* Footer */}
        <div className='mt-12 text-center'>
          <p className='text-[12px] font-semibold uppercase tracking-widest text-[#464554]'>
            Secure · Private · Encrypted
          </p>
        </div>
      </div>
    </main>
  );
};

export default LoginPage;
