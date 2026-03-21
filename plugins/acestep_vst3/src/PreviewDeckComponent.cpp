#include "PreviewDeckComponent.h"

#include "V2Chrome.h"

namespace acestep::vst3
{
PreviewDeckComponent::PreviewDeckComponent()
{
    summaryLabel_.setColour(juce::Label::textColourId, v2::kLabelPrimary);
    summaryLabel_.setJustificationType(juce::Justification::centredLeft);
    addAndMakeVisible(summaryLabel_);
    for (auto* button : {&loadButton_, &playButton_, &stopButton_, &clearButton_, &revealButton_})
    {
        addAndMakeVisible(*button);
    }
}

void PreviewDeckComponent::paint(juce::Graphics& g)
{
    v2::drawModule(g, getLocalBounds(), "Preview Deck", v2::kAccentMint);

    auto waveformZone = getLocalBounds().reduced(22).removeFromTop(24);
    juce::ignoreUnused(waveformZone);
}

void PreviewDeckComponent::resized()
{
    auto area = getLocalBounds().reduced(18);
    area.removeFromTop(24);
    summaryLabel_.setBounds(area.removeFromTop(78));
    area.removeFromTop(12);
    auto buttons = area.removeFromTop(36);
    loadButton_.setBounds(buttons.removeFromLeft(150));
    buttons.removeFromLeft(8);
    playButton_.setBounds(buttons.removeFromLeft(80));
    buttons.removeFromLeft(8);
    stopButton_.setBounds(buttons.removeFromLeft(80));
    buttons.removeFromLeft(8);
    clearButton_.setBounds(buttons.removeFromLeft(80));
    buttons.removeFromLeft(8);
    revealButton_.setBounds(buttons.removeFromLeft(120));
}

juce::TextButton& PreviewDeckComponent::loadButton() noexcept { return loadButton_; }
juce::TextButton& PreviewDeckComponent::playButton() noexcept { return playButton_; }
juce::TextButton& PreviewDeckComponent::stopButton() noexcept { return stopButton_; }
juce::TextButton& PreviewDeckComponent::clearButton() noexcept { return clearButton_; }
juce::TextButton& PreviewDeckComponent::revealButton() noexcept { return revealButton_; }

void PreviewDeckComponent::setPreviewSummary(const juce::String& summary)
{
    summaryLabel_.setText(summary, juce::dontSendNotification);
}
}  // namespace acestep::vst3
