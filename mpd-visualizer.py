import os
import sys
import numpy as np
from timeit import default_timer as timer
import asyncio
import websockets
import json

Fs = 44100
windowLength = 1024

frequencies = np.arange(windowLength / 2) * Fs / windowLength

nBars = 20

windowRate = Fs / windowLength

gamma = 2
_, splitInds = np.unique(
    np.floor(((frequencies / np.max(frequencies))**(1 / gamma)) * (nBars)), True)
splitInds = splitInds[1:]


def groupFrequencies(magnitudes):
    return np.split(magnitudes, splitInds)


def transform(channel):
    t = np.zeros(6)
    t[0] = timer()
    windowed = channel * np.hamming(channel.size)
    t[1] = timer()
    FFT = np.fft.rfft(windowed)
    t[2] = timer()
    mag = np.sqrt(FFT.real**2 + FFT.imag**2)
    t[3] = timer()
#    scaled = mag
    scaled = np.log(mag)
    t[4] = timer()
    bins = groupFrequencies(scaled)
    t[5] = timer()
    maxMag = np.zeros(nBars)
    for i in range(nBars):
        maxMag[i] = np.max(bins[i])
#        maxMag[i] = np.max(bins[i]) / 100000
    t[5] = timer()
    dt = np.diff(t)
    percents = dt / np.sum(dt)
    # print(percents)
    # print(np.sum(dt))
    return maxMag

#smoothingConstant = 0.00008
smoothingConstant = 0.000001
#smoothingConstant = 0
adjustedSmoothingConstant = smoothingConstant**(1 / windowRate)


def smooth(mag, prevSmoothedMag):
    smoothedMag = prevSmoothedMag * adjustedSmoothingConstant + \
        mag * (1 - adjustedSmoothingConstant)
    return smoothedMag


async def processAudio():
    leftChannel = np.zeros(windowLength)
    rightChannel = np.zeros(windowLength)
    sampleNum = 0
    prevSmoothedMag = np.zeros(nBars * 2)
    firstWindow = True
    prevTime = timer()
    frames = 0

    for data in sys.stdin:
        sample = data.split()
        if len(sample) == 2:
            [left, right] = sample
        else:
            left = right = 0

        leftChannel[sampleNum] = left
        rightChannel[sampleNum] = right

        if sampleNum == windowLength - 1:
            t_0 = timer()
            leftSpectrum = transform(leftChannel)
            rightSpectrum = transform(rightChannel)
            spectrum = np.concatenate(
                (leftSpectrum, np.flip(rightSpectrum)))
            if firstWindow:
                firstWindow = False
            else:
                spectrum = smooth(spectrum, prevSmoothedMag)
            prevSmoothedMag = spectrum

            t_1 = timer()
            dt = t_1 - t_0
#            print(f'FFT latency: {dt}')

            yield json.dumps(spectrum.tolist())

            frames += 1

            t = timer()
            dt = t - prevTime
            if dt >= 1:
                fps = frames / dt
                prevTime = t
                frames = 0
                print(fps)

            sampleNum = 0
        else:
            sampleNum += 1


async def sendFrame(websocket, path):
    async for frame in processAudio():
        t_0 = timer()
        await websocket.send(frame)
        t_1 = timer()
        dt = t_1 - t_0
#        print(f'web socket latency: {dt}')


asyncio.get_event_loop().run_until_complete(
    websockets.serve(sendFrame, 'localhost', 8765))
asyncio.get_event_loop().run_forever()
